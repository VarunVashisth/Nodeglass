"""Conservative lexical and local-module resolution, rerun after every scan."""

from collections import defaultdict
from pathlib import PurePosixPath

SYMBOLS = {"function", "method", "class", "variable", "parameter"}


def resolve(files, entities):
    by_id = {e.id: e for e in entities}
    by_path = {f.path: f for f in files}
    file_map = {f.id: f for f in files}
    tables = defaultdict(lambda: defaultdict(list))
    for e in entities:
        e.target_id = None
        e.target_file_id = None
        e.resolution = "resolved" if e.kind in SYMBOLS else "unresolved"
        if e.kind in SYMBOLS | {"import"}:
            tables[(e.file_id, e.scope_id)][e.name].append(e)

    def module_file(e):
        d = e.details
        module = d["module"]
        file = file_map[e.file_id]
        if file.language == "python":
            level = len(module) - len(module.lstrip("."))
            parts = list(PurePosixPath(file.path).parent.parts)
            if level:
                if level > len(parts):
                    return None
                base = parts[: len(parts) - level + 1]
            else:
                base = []
            stem = "/".join([*base, *module.lstrip(".").split(".")]).rstrip("/")
            candidates = [stem + ".py", stem + "/__init__.py"]
        else:
            if not module.startswith("."):
                return None
            path = PurePosixPath(file.path).parent / module
            normalized = []
            for part in path.parts:
                if part == "..":
                    if not normalized:
                        return None
                    normalized.pop()
                elif part != ".":
                    normalized.append(part)
            stem = "/".join(normalized)
            candidates = [stem] + [
                stem + ext
                for ext in (
                    ".ts",
                    ".tsx",
                    ".js",
                    ".jsx",
                    ".mjs",
                    "/index.ts",
                    "/index.tsx",
                    "/index.js",
                )
            ]
            if stem.endswith(".js"):
                candidates += [stem[:-3] + ".ts", stem[:-3] + ".tsx"]
        return next((by_path[p] for p in candidates if p in by_path), None)

    def lookup(e, name):
        scope = e.scope_id
        while True:
            owner = by_id.get(scope)
            if owner and owner.details.get("expression_name") == name:
                return owner, "resolved"
            candidates = tables[(e.file_id, scope)].get(name, [])
            if candidates:
                # A declaration shadows all outer bindings even before initialization.
                functions = [
                    c
                    for c in candidates
                    if c.kind in {"function", "class", "method", "import", "parameter"}
                ]
                variables = [
                    c
                    for c in candidates
                    if c.kind == "variable" and c.start_byte <= e.start_byte
                ]
                chosen = variables[-1:] if variables else functions
                return (
                    (chosen[0], "resolved")
                    if len(chosen) == 1
                    else (None, "ambiguous" if chosen else "unresolved")
                )
            if scope is None:
                return None, "unresolved"
            owner = by_id.get(scope)
            scope = owner.scope_id if owner else None
            # Class namespaces are not closures for Python method bodies.
            if (
                scope
                and file_map[e.file_id].language == "python"
                and by_id[scope].kind == "class"
            ):
                scope = by_id[scope].scope_id

    for e in entities:
        if e.kind != "import":
            continue
        target = module_file(e)
        if target:
            e.target_file_id = target.id
            e.resolution = "resolved"
            if not e.details.get("namespace"):
                imported = e.details.get("imported")
                candidates = [
                    s
                    for names in tables[(target.id, None)].values()
                    for s in names
                    if s.kind in SYMBOLS
                    and s.details.get("exported")
                    and (
                        s.name == imported
                        or imported == "default"
                        and s.details.get("default_export")
                    )
                ]
                if len(candidates) == 1:
                    e.target_id = candidates[0].id
                else:
                    e.resolution = "ambiguous" if candidates else "unresolved"
        else:
            e.resolution = (
                "unresolved" if e.details["module"].startswith(".") else "external"
            )

    def dereference(binding):
        if binding and binding.kind == "import":
            return by_id.get(binding.target_id), binding.resolution
        return binding, "resolved" if binding else "unresolved"

    def expression(e, expr, seen=None):
        seen = set() if seen is None else seen
        if "." not in expr:
            binding, status = lookup(e, expr)
            if binding:
                return dereference(binding)
            return None, status
        receiver, _, member = expr.rpartition(".")
        binding, status = lookup(e, receiver)
        if not binding:
            return None, status
        if binding.kind == "import" and binding.details.get("dotted_namespace"):
            return None, "unresolved"
        if (
            binding.kind == "import"
            and binding.details.get("namespace")
            and binding.target_file_id
        ):
            matches = [
                s
                for s in tables[(binding.target_file_id, None)].get(member, [])
                if s.details.get("exported")
            ]
        else:
            target, _ = dereference(binding)
            if (
                receiver in {"self", "cls"}
                and binding.kind == "parameter"
                and binding.scope_id
            ):
                owner = by_id[binding.scope_id]
                target = by_id.get(owner.scope_id)
            if target and target.kind == "variable" and target.id not in seen:
                # Only a direct constructor expression permits receiver inference.
                value = target.details.get("value", "")
                constructor = value.removeprefix("new ").split("(", 1)[0].strip()
                if "(" in value and constructor.isidentifier():
                    target, _ = expression(target, constructor, seen | {target.id})
            if not target or target.kind != "class":
                return None, "unresolved"
            matches = tables[(target.file_id, target.id)].get(member, [])
        return (
            (matches[0], "resolved")
            if len(matches) == 1
            else (None, "ambiguous" if matches else "unresolved")
        )

    for e in entities:
        if e.kind in {"reference", "call"}:
            target, status = expression(e, e.name)
            # Calling a variable/parameter of unknown callable type is unresolved.
            if (
                e.kind == "call"
                and target
                and target.kind not in {"function", "method", "class"}
            ):
                value = target.details.get("value")
                arrow = [
                    s
                    for s in entities
                    if s.file_id == target.file_id
                    and s.scope_id == target.scope_id
                    and s.name == target.name
                    and s.kind == "function"
                    and s.start_byte >= target.start_byte
                    and value
                    and s.end_byte <= target.end_byte + len(value.encode()) + 8
                ]
                target = arrow[0] if len(arrow) == 1 else None
                status = "resolved" if target else "unresolved"
            e.target_id = target.id if target else None
            e.resolution = status
        elif e.kind == "hook":
            handler = by_id.get(e.details.get("handler_id"))
            if not handler and e.details.get("handler"):
                handler, _ = expression(e, e.details["handler"])
            receiver = e.details.get("receiver")
            framework = e.details.get("framework_candidate")
            verified = e.name == "SCRIPT"
            if receiver:
                binding, _ = lookup(e, receiver)
                if binding and binding.kind == "variable":
                    value = binding.details.get("value", "")
                    constructor = value.removeprefix("new ").split("(", 1)[0].strip()
                    imported, _ = lookup(binding, constructor)
                    if imported and imported.kind == "import":
                        module = imported.details.get("module", "")
                        verified = (
                            framework == "fastapi"
                            and module.startswith("fastapi")
                            and imported.details.get("imported")
                            in {"FastAPI", "APIRouter"}
                        ) or (framework == "express" and module == "express")
                if framework == "event":
                    verified = e.name == "ADDEVENTLISTENER" or bool(
                        binding
                        and binding.kind == "variable"
                        and "EventEmitter" in binding.details.get("value", "")
                    )
            if verified:
                e.resolution = (
                    "resolved" if handler or e.name == "SCRIPT" else "unresolved"
                )
                e.target_id = handler.id if handler else None
                e.details = {**e.details, "verified": True}
            else:
                e.details = {**e.details, "verified": False}
        elif e.kind == "class":
            bases = []
            for base in e.details.get("bases", []):
                target, status = expression(e, base)
                bases.append(
                    {
                        "expression": base,
                        "target_id": target.id
                        if target and target.kind == "class"
                        else None,
                        "resolution": status
                        if target and target.kind == "class"
                        else "unresolved",
                    }
                )
            e.details = {**e.details, "resolved_bases": bases}
