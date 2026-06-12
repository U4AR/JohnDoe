from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import load_settings
from grid_map.atlas_builder import empty_atlas
from grid_map.storage import write_json
from grid_map.validator import validate_graph


LAYERS = {
    "normal": "normal_cv_out",
    "taxi": "taxi_cv_out",
    "bus": "bus_cv_out",
    "subway": "subway_cv_out",
}

TRANSPORT_LAYERS = ("taxi", "bus", "subway")


def main() -> None:
    settings = load_settings()
    layer_graphs = {layer: _read_graph(settings.raw_maps_dir / folder / "graph.json") for layer, folder in LAYERS.items()}
    normal_junctions = _read_junctions(settings.raw_maps_dir / LAYERS["normal"] / "junctions.csv")

    registry = build_junction_registry(normal_junctions, layer_graphs)
    game_graph = build_game_graph(registry, layer_graphs)
    errors = validate_graph(game_graph)
    if errors:
        raise SystemExit("\n".join(errors))

    metadata = build_metadata(settings.raw_maps_dir, layer_graphs)

    write_json(settings.junction_registry_path, registry)
    write_json(settings.game_graph_path, game_graph)
    write_json(settings.map_metadata_path, metadata)
    if not settings.map_atlas_path.exists():
        write_json(settings.map_atlas_path, empty_atlas())

    print(f"Wrote {settings.junction_registry_path}")
    print(f"Wrote {settings.game_graph_path}")
    print(f"Wrote {settings.map_metadata_path}")
    print(f"Atlas ready at {settings.map_atlas_path}")


def _read_graph(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_junctions(path: Path) -> dict[int, dict[str, Any]]:
    junctions: dict[int, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            junction_id = int(row["id"])
            junctions[junction_id] = {
                "id": junction_id,
                "x": int(float(row["x"])),
                "y": int(float(row["y"])),
                "radius": int(float(row["radius"])),
                "neighbors": [int(value) for value in row.get("neighbors", "").split() if value],
            }
    return junctions


def build_junction_registry(normal_junctions: dict[int, dict[str, Any]], layer_graphs: dict[str, dict]) -> dict[str, Any]:
    modes_by_junction: dict[int, set[str]] = {junction_id: set() for junction_id in normal_junctions}
    for layer, graph in layer_graphs.items():
        for node in graph.get("nodes", []):
            modes_by_junction.setdefault(int(node["id"]), set()).add(layer)

    junctions = []
    for junction_id, data in sorted(normal_junctions.items()):
        junctions.append(
            {
                "id": junction_id,
                "x": data["x"],
                "y": data["y"],
                "radius": data["radius"],
                "base_neighbors": data["neighbors"],
                "layers_present": sorted(modes_by_junction.get(junction_id, [])),
                "nearest_landmarks": [],
                "district": None,
            }
        )

    return {"schema_version": 1, "junctions": junctions}


def build_game_graph(registry: dict[str, Any], layer_graphs: dict[str, dict]) -> dict[str, Any]:
    edge_modes: dict[tuple[int, int], set[str]] = {}
    for layer in TRANSPORT_LAYERS:
        for edge in layer_graphs[layer].get("edges", []):
            source = int(edge["source"])
            target = int(edge["target"])
            key = tuple(sorted((source, target)))
            edge_modes.setdefault(key, set()).add(layer)

    edges = [
        {"source": source, "target": target, "modes": sorted(modes)}
        for (source, target), modes in sorted(edge_modes.items())
    ]
    adjacency: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        adjacency.setdefault(str(source), []).append({"destination": target, "modes": edge["modes"]})
        adjacency.setdefault(str(target), []).append({"destination": source, "modes": edge["modes"]})

    nodes = [
        {
            "id": junction["id"],
            "x": junction["x"],
            "y": junction["y"],
            "radius": junction["radius"],
        }
        for junction in registry["junctions"]
    ]
    return {"schema_version": 1, "nodes": nodes, "edges": edges, "adjacency": adjacency}


def build_metadata(raw_maps_dir: Path, layer_graphs: dict[str, dict]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "images": {layer: str(_display_image_for_layer(raw_maps_dir, layer)) for layer in LAYERS},
        "source_images": {
            "normal": str(raw_maps_dir / "images" / "normal.png"),
            "taxi": str(raw_maps_dir / "images" / "taxi.png"),
            "bus": str(raw_maps_dir / "images" / "bus.png"),
            "subway": str(raw_maps_dir / "images" / "subway.png"),
        },
        "layers": {
            layer: {
                "folder": str(raw_maps_dir / LAYERS[layer]),
                "node_count": len(graph.get("nodes", [])),
                "edge_count": len(graph.get("edges", [])),
            }
            for layer, graph in layer_graphs.items()
        },
    }


def _display_image_for_layer(raw_maps_dir: Path, layer: str) -> Path:
    folder = raw_maps_dir / LAYERS[layer]
    for candidate in (folder / "graph_on_map.png", folder / "junctions_labelled.png", raw_maps_dir / "images" / f"{layer}.png"):
        if candidate.exists():
            return candidate
    return raw_maps_dir / "images" / f"{layer}.png"


if __name__ == "__main__":
    main()
