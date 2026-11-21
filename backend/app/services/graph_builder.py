from collections import deque

from .extractor import stable


def build_graph(
    files,
    entities,
    view="dependency",
    start=None,
    direction="downstream",
    depth=2,
    limit=200,
    file_id=None,
    edge_types=None,
):
    file_map = {f.id: f for f in files}
    by_id = {e.id: e for e in entities}
    nodes, edges = {}, []

    def belongs(e, function_id):
        scope = e.scope_id
        while scope and scope != function_id:
            parent = by_id.get(scope)
            if not parent or parent.kind in {"function", "method", "class"}:
                return False
            scope = parent.scope_id
        return scope == function_id

    def node(e):
        if e.id not in nodes:
            nodes[e.id] = {
                "id": e.id,
                "type": e.kind
                if e.kind
                in {"function", "class", "method", "parameter", "variable", "control"}
                else "entry_point"
                if e.kind == "hook"
                else "unresolved",
                "label": e.name,
                "file": file_map[e.file_id].path,
                "metadata": {
                    "qualified_name": e.qualified_name,
                    "line": e.line,
                    "column": e.column,
                    "scope_id": e.scope_id,
                    "resolution": e.resolution,
                    **e.details,
                },
            }
        return e.id

    def edge(source, target, kind, entity, resolution=None, extra=None):
        edges.append(
            {
                "id": stable(entity.id, kind, source, target),
                "source": source,
                "target": target,
                "type": kind,
                "resolution": resolution or entity.resolution,
                "metadata": {
                    "line": entity.line,
                    "file": file_map[entity.file_id].path,
                    **entity.details,
                    **(extra or {}),
                },
            }
        )

    if view == "dependency":
        for f in files:
            nodes[f.id] = {
                "id": f.id,
                "type": "file",
                "label": f.path,
                "file": f.path,
                "metadata": {
                    "language": f.language,
                    "status": f.status,
                    "errors": f.errors,
                },
            }
        for e in entities:
            if e.kind == "import" and e.target_file_id:
                edge(e.file_id, e.target_file_id, "IMPORTS", e, "resolved")
        if file_id and not start:
            start = file_id
    elif view == "calls":
        for e in entities:
            if e.kind in {"function", "method", "class"}:
                node(e)
            if (
                e.kind in {"function", "method"}
                and e.scope_id in by_id
                and by_id[e.scope_id].kind in {"function", "method", "class"}
            ):
                edge(node(by_id[e.scope_id]), node(e), "CONTAINS", e, "resolved")
            if e.kind == "call":
                caller = by_id.get(e.scope_id)
                while caller and caller.kind not in {"function", "method"}:
                    caller = by_id.get(caller.scope_id)
                if caller:
                    source = node(caller)
                else:
                    source = e.file_id
                    nodes[source] = {
                        "id": source,
                        "type": "module",
                        "label": file_map[source].path,
                        "file": file_map[source].path,
                        "metadata": {},
                    }
                target = by_id.get(e.target_id)
                if target:
                    target_id = node(target)
                else:
                    target_id = "unresolved:" + e.id
                    nodes[target_id] = {
                        "id": target_id,
                        "type": "external"
                        if e.resolution == "external"
                        else "unresolved",
                        "label": e.name,
                        "file": file_map[e.file_id].path,
                        "metadata": {"resolution": e.resolution, "line": e.line},
                    }
                edge(source, target_id, "CALLS", e)
            elif e.kind == "hook" and e.details.get("verified"):
                source = node(e)
                if e.target_id in by_id:
                    edge(source, node(by_id[e.target_id]), "TRIGGERS", e)
                elif e.name == "SCRIPT":
                    for call in entities:
                        if (
                            call.kind == "call"
                            and e.details["control_id"]
                            in call.details.get("controls", [])
                            and call.target_id
                        ):
                            edge(
                                source,
                                node(by_id[call.target_id]),
                                "TRIGGERS",
                                call,
                                "resolved",
                            )
            elif e.kind == "class":
                for base in e.details.get("resolved_bases", []):
                    if base["target_id"] in by_id:
                        edge(
                            node(e),
                            node(by_id[base["target_id"]]),
                            "INHERITS",
                            e,
                            "resolved",
                        )
    else:
        function = by_id.get(start)
        if not function or function.kind not in {"function", "method"}:
            return {
                "nodes": [],
                "edges": [],
                "truncated": False,
                "warning": "Select a function to inspect its flow.",
            }
        node(function)
        statements = sorted(
            [
                e
                for e in entities
                if belongs(e, start)
                and e.kind in {"assignment", "return", "control", "call"}
            ],
            key=lambda e: (e.start_byte, -e.end_byte),
        )
        for e in statements:
            node(e)
            nodes[e.id]["type"] = (
                "control"
                if e.kind == "control"
                else "variable"
                if e.kind == "assignment"
                else "unresolved"
                if e.kind == "call" and not e.target_id
                else "control"
            )
            nodes[e.id]["metadata"]["statement_kind"] = e.kind
            # Containment is explicit; no fabricated sequential order between branches.
            controls = e.details.get("controls", [])
            parent = controls[-1] if controls else e.details.get("parent_control")
            edge(parent if parent in nodes else start, e.id, "CONTAINS", e, "resolved")
            if e.kind == "control":
                edge(
                    parent if parent in nodes else start,
                    e.id,
                    "CONTROL_FLOW",
                    e,
                    "inferred",
                    {"meaning": "possible entry into construct"},
                )
            if e.kind == "return":
                edge(e.id, start, "RETURNS", e, "resolved")
            if e.kind == "assignment":
                for binding in entities:
                    if (
                        binding.kind == "variable"
                        and belongs(binding, start)
                        and e.start_byte <= binding.start_byte < e.end_byte
                    ):
                        edge(e.id, node(binding), "ASSIGNS", e, "resolved")
                for ref in entities:
                    if (
                        ref.kind == "reference"
                        and belongs(ref, start)
                        and e.start_byte <= ref.start_byte < e.end_byte
                        and ref.target_id
                    ):
                        target = by_id[ref.target_id]
                        if (
                            target.start_byte < e.start_byte
                            or target.kind == "parameter"
                        ):
                            edge(e.id, node(target), "DATA_DEPENDS_ON", ref, "inferred")
        for e in entities:
            if e.scope_id == start and e.kind == "parameter":
                node(e)
                edge(start, e.id, "DEFINES", e, "resolved")
    if edge_types:
        edges = [e for e in edges if e["type"] in edge_types]
    if view != "flow" and start:
        adjacency = {}
        for e in edges:
            source, target = (
                (e["source"], e["target"])
                if direction == "downstream"
                else (e["target"], e["source"])
            )
            adjacency.setdefault(source, set()).add(target)
        reached = {start} if start in nodes else set()
        traversal_order = [start] if start in nodes else []
        queue = deque([(start, 0)])
        while queue:
            current, distance = queue.popleft()
            if distance >= depth:
                continue
            for target in sorted(adjacency.get(current, [])):
                if target not in reached:
                    reached.add(target)
                    traversal_order.append(target)
                    queue.append((target, distance + 1))
        nodes = {key: nodes[key] for key in traversal_order if key in nodes}
    elif file_id and view == "calls":
        matching = {e.id for e in entities if e.file_id == file_id}
        matching.add(file_id)
        matching.update(e["target"] for e in edges if e["source"] in matching)
        nodes = {k: v for k, v in nodes.items() if k in matching}
    truncated = len(nodes) > limit
    nodes = dict(list(nodes.items())[:limit])
    edges = [e for e in edges if e["source"] in nodes and e["target"] in nodes]
    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "truncated": truncated,
        "warning": f"Graph limited to {limit} nodes. Focus a symbol or file."
        if truncated
        else None,
    }
