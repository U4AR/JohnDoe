from __future__ import annotations


def validate_graph(graph: dict) -> list[str]:
    errors: list[str] = []
    node_ids = {int(node["id"]) for node in graph.get("nodes", [])}

    for edge in graph.get("edges", []):
        source = int(edge["source"])
        target = int(edge["target"])
        if source not in node_ids:
            errors.append(f"Edge source {source} is missing from nodes")
        if target not in node_ids:
            errors.append(f"Edge target {target} is missing from nodes")
        if not edge.get("modes"):
            errors.append(f"Edge {source}-{target} has no transport modes")

    return errors

