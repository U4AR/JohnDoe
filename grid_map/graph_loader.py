from __future__ import annotations

from config import load_settings
from .models import LegalMove
from .storage import read_json


def load_game_graph() -> dict:
    settings = load_settings()
    return read_json(settings.game_graph_path)


def all_junction_ids() -> list[int]:
    graph = load_game_graph()
    return sorted(int(node["id"]) for node in graph.get("nodes", []))


def adjacent_junctions(junction_id: int) -> list[int]:
    graph = load_game_graph()
    adjacency = graph.get("adjacency", {}).get(str(junction_id), [])
    return sorted({int(item["destination"]) for item in adjacency})


def legal_moves_from(junction_id: int, blocked_edges: list[dict] | None = None) -> list[LegalMove]:
    graph = load_game_graph()
    blocked_edges = blocked_edges or []
    moves: list[LegalMove] = []

    for edge in graph.get("edges", []):
        source = int(edge["source"])
        target = int(edge["target"])
        if junction_id not in (source, target):
            continue

        destination = target if source == junction_id else source
        for mode in edge.get("modes", []):
            blocked = _is_blocked(junction_id, destination, mode, blocked_edges)
            moves.append(LegalMove(destination=destination, via=(junction_id, destination), mode=mode, blocked=blocked))

    return sorted(moves, key=lambda move: (move.destination, move.mode))


def _is_blocked(source: int, target: int, mode: str, blocks: list[dict]) -> bool:
    for block in blocks:
        block_type = block.get("block_type")
        if block_type == "mode_block" and block.get("mode") == mode:
            return True
        if block_type == "junction_block" and block.get("junction_id") in (source, target):
            return True
        if block_type == "edge_block":
            same_edge = {block.get("from_junction"), block.get("to_junction")} == {source, target}
            same_mode = block.get("mode") in (None, mode)
            if same_edge and same_mode:
                return True
    return False
