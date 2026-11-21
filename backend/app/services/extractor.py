"""Language-specific Tree-sitter extraction; no source execution or text parsing."""

from hashlib import sha256

from .parser import walk

FUNCTIONS = {
    "function_definition",
    "function_declaration",
    "generator_function_declaration",
    "method_definition",
    "arrow_function",
    "function_expression",
    "generator_function",
}
CLASSES = {"class_definition", "class_declaration", "class"}
CONTROLS = {
    "if_statement",
    "elif_clause",
    "else_clause",
    "for_statement",
    "for_in_statement",
    "while_statement",
    "do_statement",
    "try_statement",
    "except_clause",
    "catch_clause",
    "finally_clause",
    "switch_statement",
    "switch_case",
    "conditional_expression",
    "await",
    "await_expression",
    "yield",
    "yield_expression",
    "break_statement",
    "continue_statement",
}


def stable(*parts):
    return sha256("|".join(map(str, parts)).encode()).hexdigest()[:32]


def extract(repository_id, file_id, source, tree, language):
    result = []
    definitions = set()
    scopes = {}
    identities = {}
    python = language == "python"

    def text(n):
        return source[n.start_byte : n.end_byte].decode("utf-8") if n else ""

    def field(n, key):
        return n.child_by_field_name(key)

    def add(n, kind, name, scope, details=None, qname=None):
        identity = stable(file_id, kind, n.start_byte, name)
        occurrence = identities.get(identity, 0)
        identities[identity] = occurrence + 1
        item = {
            "id": stable(identity, occurrence) if occurrence else identity,
            "repository_id": repository_id,
            "file_id": file_id,
            "kind": kind,
            "name": name,
            "qualified_name": qname or name,
            "scope_id": scope,
            "start_byte": n.start_byte,
            "end_byte": n.end_byte,
            "line": n.start_point.row + 1,
            "column": n.start_point.column,
            "end_line": n.end_point.row + 1,
            "end_column": n.end_point.column,
            "details": details or {},
            "resolution": "unresolved",
        }
        result.append(item)
        return item

    def bindings(n):
        if n is None:
            return []
        if n.type in {"identifier", "shorthand_property_identifier_pattern"}:
            return [n]
        if n.type in {
            "attribute",
            "member_expression",
            "subscript",
            "subscript_expression",
        }:
            return []
        if n.type in {
            "typed_parameter",
            "typed_default_parameter",
            "default_parameter",
            "required_parameter",
            "optional_parameter",
            "assignment_pattern",
            "pair_pattern",
        }:
            child = (
                field(n, "name")
                or field(n, "pattern")
                or field(n, "left")
                or field(n, "value")
            )
            if child:
                return bindings(child)
            return bindings(n.named_children[0]) if n.named_children else []
        return [
            b
            for c in n.named_children
            if c.type not in {"type_annotation", "type"}
            for b in bindings(c)
        ]

    def visit(n, scope=None, prefix="", conditions=()):
        if (
            not python
            and n.type == "statement_block"
            and n.parent
            and n.parent.type not in FUNCTIONS
        ):
            block = add(n, "scope", "<block>", scope)
            scopes[block["id"]] = block
            scope = block["id"]
        if n.type in FUNCTIONS | CLASSES:
            is_class = n.type in CLASSES
            name_node = field(n, "name")
            expression_name = (
                text(name_node)
                if n.type in {"function_expression", "generator_function"}
                else ""
            )
            if (
                n.type in {"function_expression", "generator_function"}
                and n.parent
                and n.parent.type in {"variable_declarator", "assignment"}
            ):
                name_node = (
                    field(n.parent, "name") or field(n.parent, "left") or name_node
                )
            if (
                not name_node
                and n.parent
                and n.parent.type in {"variable_declarator", "assignment", "pair"}
            ):
                name_node = (
                    field(n.parent, "name")
                    or field(n.parent, "left")
                    or field(n.parent, "key")
                )
            name = (
                text(name_node)
                or f"<anonymous@{n.start_point.row + 1}:{n.start_point.column}>"
            )
            if name_node:
                definitions.add(name_node.id)
            parent = scopes.get(scope)
            kind = (
                "class"
                if is_class
                else ("method" if parent and parent["kind"] == "class" else "function")
            )
            parameters = field(n, "parameters")
            param_nodes = (
                parameters.named_children
                if parameters
                else ([field(n, "parameter")] if field(n, "parameter") else [])
            )
            decorators = []
            if n.parent and n.parent.type == "decorated_definition":
                decorators = [
                    text(c) for c in n.parent.named_children if c.type == "decorator"
                ]
            bases = field(n, "superclasses") or next(
                (c for c in n.named_children if c.type == "class_heritage"), None
            )
            body = field(n, "body")
            item = add(
                n,
                kind,
                name,
                scope,
                {
                    "parameters": [text(c) for c in param_nodes],
                    "return_annotation": text(field(n, "return_type")),
                    "decorators": decorators,
                    "expression_name": expression_name,
                    "async": any(c.type == "async" for c in n.children),
                    "bases": [
                        text(field(c, "value") or c) for c in bases.named_children
                    ]
                    if bases
                    else [],
                    "body_range": [body.start_byte, body.end_byte] if body else None,
                    "exported": python
                    or bool(
                        n.parent
                        and (
                            n.parent.type == "export_statement"
                            or n.parent.type == "variable_declarator"
                            and n.parent.parent
                            and n.parent.parent.parent
                            and n.parent.parent.parent.type == "export_statement"
                        )
                    ),
                    "default_export": bool(
                        n.parent
                        and n.parent.type == "export_statement"
                        and any(c.type == "default" for c in n.parent.children)
                    ),
                },
                prefix + name,
            )
            scopes[item["id"]] = item
            for p in param_nodes:
                for b in bindings(p):
                    definitions.add(b.id)
                    add(
                        b,
                        "parameter",
                        text(b),
                        item["id"],
                        {"declaration": text(p)},
                        prefix + name + "." + text(b),
                    )
            # Defaults/decorators execute in outer scope; bodies introduce lexical scope.
            if body:
                if n.type == "arrow_function" and body.type != "statement_block":
                    add(
                        body,
                        "return",
                        text(body),
                        item["id"],
                        {"implicit": True, "controls": []},
                    )
                visit(body, item["id"], prefix + name + ".", ())
            if not is_class:
                for d in (
                    n.parent.named_children
                    if n.parent and n.parent.type == "decorated_definition"
                    else []
                ):
                    if d.type != "decorator":
                        continue
                    call = next(
                        (c for c in walk(d) if c.type in {"call", "call_expression"}),
                        None,
                    )
                    if call:
                        callee = text(field(call, "function"))
                        args = field(call, "arguments")
                        method = callee.rsplit(".", 1)[-1]
                        if (
                            method
                            in {
                                "get",
                                "post",
                                "put",
                                "patch",
                                "delete",
                                "options",
                                "head",
                                "on_event",
                            }
                            and args
                            and args.named_children
                        ):
                            first = args.named_children[0]
                            if first.type == "string":
                                add(
                                    d,
                                    "hook",
                                    method.upper(),
                                    scope,
                                    {
                                        "receiver": callee.rsplit(".", 1)[0],
                                        "path": text(first)[1:-1],
                                        "handler_id": item["id"],
                                        "framework_candidate": "fastapi",
                                    },
                                )
            return

        if n.type in {"import_statement", "import_from_statement"} and python:
            module = field(n, "module_name")
            names = n.children_by_field_name("name")
            for target in names:
                alias = field(target, "alias")
                original = (
                    field(target, "name") if target.type == "aliased_import" else target
                )
                name = text(original)
                local = text(alias) or (name.split(".")[0] if module is None else name)
                add(
                    n,
                    "import",
                    local,
                    scope,
                    {
                        "module": text(module) if module else name,
                        "imported": name if module else None,
                        "alias": text(alias),
                        "level": len(text(module)) - len(text(module).lstrip(".")),
                        "namespace": module is None,
                        "dotted_namespace": module is None
                        and "." in name
                        and not alias,
                    },
                )
            if any(c.type == "wildcard_import" for c in n.named_children):
                add(
                    n,
                    "import",
                    "*",
                    scope,
                    {"module": text(module), "imported": "*", "namespace": False},
                )
            return
        if n.type == "import_statement" and not python:
            src = field(n, "source")
            clause = next(
                (c for c in n.named_children if c.type == "import_clause"), None
            )
            if not clause:
                add(
                    n,
                    "import",
                    "",
                    scope,
                    {"module": text(src)[1:-1], "imported": None, "namespace": True},
                )
            else:
                for c in clause.named_children:
                    if c.type == "identifier":
                        add(
                            c,
                            "import",
                            text(c),
                            scope,
                            {
                                "module": text(src)[1:-1],
                                "imported": "default",
                                "namespace": False,
                            },
                        )
                    elif c.type == "namespace_import":
                        add(
                            c,
                            "import",
                            text(c.named_children[-1]),
                            scope,
                            {
                                "module": text(src)[1:-1],
                                "imported": None,
                                "namespace": True,
                            },
                        )
                    elif c.type == "named_imports":
                        for spec in c.named_children:
                            original = field(spec, "name")
                            alias = field(spec, "alias")
                            add(
                                spec,
                                "import",
                                text(alias or original),
                                scope,
                                {
                                    "module": text(src)[1:-1],
                                    "imported": text(original),
                                    "namespace": False,
                                },
                            )
            return

        next_conditions = conditions
        if n.type in CONTROLS:
            condition = text(field(n, "condition") or field(n, "value"))
            control = add(
                n,
                "control",
                n.type,
                scope,
                {
                    "condition": condition,
                    "parent_control": conditions[-1] if conditions else None,
                },
            )
            if n.type not in {
                "await",
                "await_expression",
                "yield",
                "yield_expression",
                "break_statement",
                "continue_statement",
            }:
                next_conditions = (*conditions, control["id"])
            if (
                python
                and n.type == "if_statement"
                and condition in {'__name__ == "__main__"', "__name__ == '__main__'"}
            ):
                add(
                    n,
                    "hook",
                    "SCRIPT",
                    scope,
                    {"path": "__main__", "control_id": control["id"]},
                )
        if n.type in {"call", "call_expression", "new_expression"}:
            callee = field(n, "function") or field(n, "constructor")
            args = field(n, "arguments")
            add(
                n,
                "call",
                text(callee),
                scope,
                {
                    "arguments": [text(c) for c in args.named_children] if args else [],
                    "conditional": bool(conditions),
                    "controls": list(conditions),
                    "constructor": n.type == "new_expression",
                },
            )
            if not python and callee and callee.type == "member_expression" and args:
                receiver = text(field(callee, "object"))
                method = text(field(callee, "property"))
                values = args.named_children
                if (
                    method
                    in {
                        "get",
                        "post",
                        "put",
                        "patch",
                        "delete",
                        "use",
                        "on",
                        "addEventListener",
                    }
                    and len(values) >= 2
                    and values[0].type == "string"
                ):
                    add(
                        n,
                        "hook",
                        method.upper(),
                        scope,
                        {
                            "receiver": receiver,
                            "path": text(values[0])[1:-1],
                            "handler": text(values[-1]),
                            "framework_candidate": "express"
                            if method not in {"on", "addEventListener"}
                            else "event",
                        },
                    )
        if n.type in {
            "assignment",
            "augmented_assignment",
            "variable_declarator",
            "assignment_expression",
            "augmented_assignment_expression",
        }:
            left = field(n, "left") or field(n, "name")
            right = field(n, "right") or field(n, "value")
            add(
                n,
                "assignment",
                text(left),
                scope,
                {
                    "value": text(right),
                    "operator": text(field(n, "operator")) or "=",
                    "controls": list(conditions),
                },
            )
            # Chained assignments are traversed independently.
            for b in bindings(left):
                definitions.add(b.id)
                if right and right.type in FUNCTIONS:
                    continue
                binding_scope = scope
                if not python and n.parent and n.parent.type == "variable_declaration":
                    while binding_scope and scopes[binding_scope]["kind"] == "scope":
                        binding_scope = scopes[binding_scope]["scope_id"]
                add(
                    b,
                    "variable",
                    text(b),
                    binding_scope,
                    {
                        "value": text(right),
                        "exported": python
                        or bool(
                            n.parent
                            and n.parent.parent
                            and n.parent.parent.type == "export_statement"
                        ),
                    },
                    prefix + text(b),
                )
        if n.type == "return_statement":
            add(
                n,
                "return",
                text(n)[6:].strip().rstrip(";"),
                scope,
                {"controls": list(conditions)},
            )
        if (
            n.type in {"identifier", "shorthand_property_identifier"}
            and n.id not in definitions
        ):
            parent = n.parent
            excluded = parent and (
                (
                    parent.type in {"attribute", "member_expression"}
                    and (
                        field(parent, "attribute") == n
                        or field(parent, "property") == n
                    )
                )
                or parent.type in {"type_annotation", "pair", "labeled_statement"}
            )
            if not excluded:
                add(n, "reference", text(n), scope)
        for c in n.named_children:
            visit(c, scope, prefix, next_conditions)

    visit(tree.root_node)
    errors = [
        {
            "line": n.start_point.row + 1,
            "column": n.start_point.column,
            "type": n.type,
            "start_byte": n.start_byte,
            "end_byte": n.end_byte,
        }
        for n in all_nodes(tree.root_node)
        if n.type == "ERROR" or n.is_missing
    ]
    return result, errors


def all_nodes(node):
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))
