#!/usr/bin/env python3
"""
Interactive map correction server for the Scotland Yard map digitizer outputs.

Run from this directory:
    python map_editor.py

Then open the printed localhost URL. The UI keeps one shared junction set across
all maps, while each map keeps its own transport-route edges.
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
import math
import mimetypes
import shutil
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import cv2
import networkx as nx


ROOT = Path(__file__).resolve().parent
UI_ROOT = ROOT / "map_editor_ui"
BACKUP_ROOT = ROOT / "editor_backups"

MAPS: list[dict[str, str]] = [
    {
        "key": "map",
        "label": "Full Map",
        "image": "Map.png",
        "folder": "map_cv_out",
        "color": "#365fcb",
    },
    {
        "key": "taxi",
        "label": "Taxi",
        "image": "Taxi.png",
        "folder": "taxi_cv_out",
        "color": "#d7a81f",
    },
    {
        "key": "bus",
        "label": "Bus",
        "image": "Bus.png",
        "folder": "bus_cv_out",
        "color": "#24985f",
    },
    {
        "key": "subway",
        "label": "Subway",
        "image": "Subway.png",
        "folder": "subway_cv_out",
        "color": "#d6463e",
    },
]
TRANSPORT_KEYS = {"taxi", "bus", "subway"}
PREVIEW_IMAGE_NAME = "graph_on_map.png"


def _json_response(handler: SimpleHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    body = json.dumps(payload, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(handler: SimpleHTTPRequestHandler, text: str, status: int = 200) -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def load_graph_for(map_info: dict[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    folder = ROOT / map_info["folder"]
    graph_path = folder / "graph.json"
    csv_path = folder / "junctions.csv"

    if graph_path.exists():
        with graph_path.open("r", encoding="utf-8") as f:
            graph = json.load(f)
        nodes = [
            {
                "uid": f"n{int(node['id'])}",
                "id": int(node["id"]),
                "x": int(round(float(node["x"]))),
                "y": int(round(float(node["y"]))),
                "r": int(round(float(node.get("r", node.get("radius", 12))))),
            }
            for node in graph.get("nodes", [])
        ]
        edges = normalize_edges(graph.get("edges", []))
        if edges:
            return sorted(nodes, key=lambda n: n["id"]), edges

        adjacency_edges: list[dict[str, str]] = []
        for source, targets in graph.get("adjacency", {}).items():
            for target in targets:
                adjacency_edges.append({"source": source, "target": target})
        return sorted(nodes, key=lambda n: n["id"]), normalize_edges(adjacency_edges)

    if csv_path.exists():
        nodes: list[dict[str, Any]] = []
        raw_edges: list[dict[str, str]] = []
        with csv_path.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                node_id = int(row["id"])
                nodes.append(
                    {
                        "uid": f"n{node_id}",
                        "id": node_id,
                        "x": int(round(float(row["x"]))),
                        "y": int(round(float(row["y"]))),
                        "r": int(round(float(row.get("radius") or row.get("r") or 12))),
                    }
                )
                for neighbor in (row.get("neighbors") or "").split():
                    raw_edges.append({"source": str(node_id), "target": neighbor})
        return sorted(nodes, key=lambda n: n["id"]), normalize_edges(raw_edges)

    return [], []


def normalize_edges(raw_edges: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    edges: list[dict[str, str]] = []
    for edge in raw_edges:
        source = str(edge.get("source", edge.get("from", ""))).strip()
        target = str(edge.get("target", edge.get("to", ""))).strip()
        if not source or not target or source == target:
            continue
        source_uid = source if source.startswith("n") or source.startswith("u") else f"n{int(source)}"
        target_uid = target if target.startswith("n") or target.startswith("u") else f"n{int(target)}"
        a, b = sorted([source_uid, target_uid])
        if (a, b) in seen:
            continue
        seen.add((a, b))
        edges.append({"source": a, "target": b})
    return edges


def get_image_size(image_name: str) -> dict[str, int]:
    img = cv2.imread(str(ROOT / image_name))
    if img is None:
        return {"width": 0, "height": 0}
    height, width = img.shape[:2]
    return {"width": int(width), "height": int(height)}


def build_state() -> dict[str, Any]:
    loaded: dict[str, tuple[list[dict[str, Any]], list[dict[str, str]]]] = {}
    for map_info in MAPS:
        loaded[map_info["key"]] = load_graph_for(map_info)

    # Prefer the visual "Map" output as the shared editable master, then fill any
    # missing IDs from the other maps so no existing edges are stranded.
    shared_by_id: dict[int, dict[str, Any]] = {}
    for key in ["map", "taxi", "bus", "subway"]:
        for node in loaded[key][0]:
            shared_by_id.setdefault(int(node["id"]), dict(node))

    nodes = [shared_by_id[node_id] for node_id in sorted(shared_by_id)]
    maps_payload: list[dict[str, Any]] = []
    for map_info in MAPS:
        size = get_image_size(map_info["image"])
        maps_payload.append(
            {
                **map_info,
                "imageUrl": f"/images/{map_info['image']}",
                **size,
            }
        )

    return {
        "maps": maps_payload,
        "nodes": nodes,
        "edges": {key: loaded[key][1] for key in loaded},
        "master": "map",
    }


def ensure_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def validated_payload(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, str]]]]:
    nodes: list[dict[str, Any]] = []
    seen_uids: set[str] = set()
    for index, raw in enumerate(payload.get("nodes", []), start=1):
        uid = str(raw.get("uid") or f"u{index}")
        if uid in seen_uids:
            continue
        seen_uids.add(uid)
        nodes.append(
            {
                "uid": uid,
                "id": ensure_int(raw.get("id"), index),
                "x": ensure_int(raw.get("x")),
                "y": ensure_int(raw.get("y")),
                "r": max(5, ensure_int(raw.get("r"), 12)),
            }
        )

    nodes.sort(key=lambda n: n["id"])
    uid_to_id = {node["uid"]: int(node["id"]) for node in nodes}

    edges_by_map: dict[str, list[dict[str, str]]] = {}
    for map_info in MAPS:
        key = map_info["key"]
        edges_by_map[key] = normalize_edges(
            [
                edge
                for edge in payload.get("edges", {}).get(key, [])
                if edge.get("source") in uid_to_id and edge.get("target") in uid_to_id
            ]
        )
    return nodes, edges_by_map


def backup_outputs() -> Path:
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / stamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    for map_info in MAPS:
        source_folder = ROOT / map_info["folder"]
        target_folder = backup_dir / map_info["folder"]
        target_folder.mkdir(parents=True, exist_ok=True)
        for name in ["junctions.csv", "graph.json", "graph.graphml", "junctions_labelled.png", PREVIEW_IMAGE_NAME]:
            source = source_folder / name
            if source.exists():
                shutil.copy2(source, target_folder / name)
    return backup_dir


def write_outputs(nodes: list[dict[str, Any]], edges: list[dict[str, str]], map_info: dict[str, str]) -> None:
    out_dir = ROOT / map_info["folder"]
    out_dir.mkdir(parents=True, exist_ok=True)
    uid_to_id = {node["uid"]: int(node["id"]) for node in nodes}
    id_to_node = {int(node["id"]): node for node in nodes}

    graph_edges: set[tuple[int, int]] = set()
    for edge in edges:
        source_id = uid_to_id.get(edge["source"])
        target_id = uid_to_id.get(edge["target"])
        if source_id is None or target_id is None or source_id == target_id:
            continue
        graph_edges.add(tuple(sorted((source_id, target_id))))

    graph = nx.Graph()
    for node in sorted(nodes, key=lambda n: int(n["id"])):
        graph.add_node(
            int(node["id"]),
            x=int(node["x"]),
            y=int(node["y"]),
            r=int(node["r"]),
        )
    graph.add_edges_from(sorted(graph_edges))

    with (out_dir / "junctions.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "x", "y", "radius", "neighbors"])
        for node_id in sorted(id_to_node):
            node = id_to_node[node_id]
            neighbors = " ".join(str(n) for n in sorted(graph.neighbors(node_id)))
            writer.writerow([node_id, node["x"], node["y"], node["r"], neighbors])

    graph_json = {
        "nodes": [
            {"id": int(node_id), "x": int(node["x"]), "y": int(node["y"]), "r": int(node["r"])}
            for node_id, node in sorted(id_to_node.items())
        ],
        "edges": [{"source": int(a), "target": int(b)} for a, b in sorted(graph_edges)],
        "adjacency": {str(node_id): sorted(int(n) for n in graph.neighbors(node_id)) for node_id in sorted(id_to_node)},
    }
    with (out_dir / "graph.json").open("w", encoding="utf-8") as f:
        json.dump(graph_json, f, indent=2)
        f.write("\n")

    nx.write_graphml(graph, out_dir / "graph.graphml")
    write_labelled_image(nodes, map_info)


def write_labelled_image(nodes: list[dict[str, Any]], map_info: dict[str, str]) -> None:
    img = cv2.imread(str(ROOT / map_info["image"]))
    if img is None:
        return

    for node in nodes:
        node_id = int(node["id"])
        x = int(node["x"])
        y = int(node["y"])
        radius = int(node["r"])
        label = str(node_id)
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.50 if len(label) < 3 else 0.40
        thickness = 1
        (tw, th), _ = cv2.getTextSize(label, font, scale, thickness)
        text_radius = int(math.ceil(math.hypot(tw / 2.0, th / 2.0)))
        draw_radius = max(radius + 3, text_radius + 3)
        cv2.circle(img, (x, y), draw_radius, (245, 225, 160), -1)
        cv2.putText(
            img,
            label,
            (x - tw // 2, y + th // 2),
            font,
            scale,
            (20, 20, 20),
            thickness,
            cv2.LINE_AA,
        )

    cv2.imwrite(str(ROOT / map_info["folder"] / "junctions_labelled.png"), img)


def hex_to_bgr(color: str) -> tuple[int, int, int]:
    clean = color.strip().lstrip("#")
    if len(clean) != 6:
        return (40, 40, 40)
    red = int(clean[0:2], 16)
    green = int(clean[2:4], 16)
    blue = int(clean[4:6], 16)
    return (blue, green, red)


def write_graph_on_map_preview(nodes: list[dict[str, Any]], edges: list[dict[str, str]], map_info: dict[str, str]) -> Path:
    """Draw one transport graph over the normal Map.png image and save it."""
    base = cv2.imread(str(ROOT / "Map.png"))
    if base is None:
        raise ValueError("Could not read Map.png for preview generation.")

    title_h = 86
    height, width = base.shape[:2]
    preview = cv2.copyMakeBorder(base, title_h, 0, 0, 0, cv2.BORDER_CONSTANT, value=(242, 231, 206))
    color = hex_to_bgr(map_info["color"])
    uid_to_node = {node["uid"]: node for node in nodes}

    overlay = preview.copy()
    for edge in edges:
        source = uid_to_node.get(edge["source"])
        target = uid_to_node.get(edge["target"])
        if not source or not target:
            continue
        a = (int(source["x"]), int(source["y"]) + title_h)
        b = (int(target["x"]), int(target["y"]) + title_h)
        cv2.line(overlay, a, b, color, 9, cv2.LINE_AA)
        cv2.line(overlay, a, b, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.78, preview, 0.22, 0, preview)

    for node in nodes:
        x = int(node["x"])
        y = int(node["y"]) + title_h
        node_id = int(node["id"])
        radius = max(int(node["r"]) + 2, 13)
        cv2.circle(preview, (x, y), radius, (245, 225, 160), -1, cv2.LINE_AA)
        cv2.circle(preview, (x, y), radius, (35, 30, 24), 2, cv2.LINE_AA)
        label = str(node_id)
        scale = 0.46 if len(label) < 3 else 0.37
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
        cv2.putText(
            preview,
            label,
            (x - tw // 2, y + th // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            (18, 18, 18),
            1,
            cv2.LINE_AA,
        )

    title = f"{map_info['label']} Routes"
    subtitle = "     "
    cv2.rectangle(preview, (0, 0), (width, title_h), (242, 231, 206), -1)
    cv2.line(preview, (0, title_h - 1), (width, title_h - 1), color, 5, cv2.LINE_AA)
    cv2.putText(preview, title, (34, 42), cv2.FONT_HERSHEY_DUPLEX, 1.25, (30, 28, 23), 2, cv2.LINE_AA)
    cv2.putText(preview, subtitle, (36, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (92, 88, 74), 1, cv2.LINE_AA)

    out_path = ROOT / map_info["folder"] / PREVIEW_IMAGE_NAME
    cv2.imwrite(str(out_path), preview)
    return out_path


def save_state(payload: dict[str, Any]) -> dict[str, Any]:
    nodes, edges_by_map = validated_payload(payload)
    if not nodes:
        raise ValueError("Cannot save an empty junction set.")

    backup_dir = backup_outputs()
    for map_info in MAPS:
        write_outputs(nodes, edges_by_map[map_info["key"]], map_info)

    return {
        "ok": True,
        "nodeCount": len(nodes),
        "edgeCounts": {key: len(edges) for key, edges in edges_by_map.items()},
        "backup": str(backup_dir.relative_to(ROOT)),
    }


def save_previews(payload: dict[str, Any]) -> dict[str, Any]:
    nodes, edges_by_map = validated_payload(payload)
    if not nodes:
        raise ValueError("Cannot render previews for an empty junction set.")

    backup_dir = backup_outputs()
    saved: dict[str, str] = {}
    for map_info in MAPS:
        if map_info["key"] not in TRANSPORT_KEYS:
            continue
        out_path = write_graph_on_map_preview(nodes, edges_by_map[map_info["key"]], map_info)
        saved[map_info["key"]] = str(out_path.relative_to(ROOT))

    return {
        "ok": True,
        "saved": saved,
        "backup": str(backup_dir.relative_to(ROOT)),
    }


class MapEditorHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("map-editor: " + fmt % args + "\n")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/state":
            _json_response(self, build_state())
            return
        if path == "/":
            self._serve_file(UI_ROOT / "index.html")
            return
        if path.startswith("/static/"):
            self._serve_file(UI_ROOT / path.removeprefix("/static/"))
            return
        if path.startswith("/images/"):
            image_name = Path(path.removeprefix("/images/")).name
            if image_name not in {m["image"] for m in MAPS}:
                _text_response(self, "Unknown image", 404)
                return
            self._serve_file(ROOT / image_name)
            return
        _text_response(self, "Not found", 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/save", "/api/save-previews"}:
            _text_response(self, "Not found", 404)
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
            if parsed.path == "/api/save":
                result = save_state(payload)
            else:
                result = save_previews(payload)
        except Exception as exc:  # Keep the browser error readable during local editing.
            _json_response(self, {"ok": False, "error": str(exc)}, 400)
            return
        _json_response(self, result)

    def _serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            _text_response(self, "Not found", 404)
            return
        data = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the interactive map correction UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open the editor in your default browser.")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), MapEditorHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Map editor running at {url}")
    print("Press Ctrl+C to stop.")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping map editor.")


if __name__ == "__main__":
    main()
