#!/usr/bin/env python3
"""
Detect circular taxi-map junctions, build a graph of direct road connections,
and create a labelled junction image without drawing connection lines.

Example:
    python taxi_map_cv_graph.py --image Taxi.png --out out --show-labels
"""

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import cv2
import networkx as nx
import numpy as np
from skimage.morphology import skeletonize


def merge_circles(circles, min_dist=14):
    """Merge duplicate Hough detections, preferring larger/stronger circles."""
    if not circles:
        return []
    circles = sorted(circles, key=lambda c: c[2], reverse=True)
    kept = []
    for x, y, r in circles:
        if all(math.hypot(x - k[0], y - k[1]) > min_dist for k in kept):
            kept.append((int(x), int(y), int(r)))
    # Stable numbering: top-to-bottom, then left-to-right.
    kept.sort(key=lambda c: (c[1], c[0]))
    return kept


def detect_junctions(img_bgr, args):
    """Detect circular junction disks with Hough circles plus sanity filtering."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)

    raw = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=args.hough_dp,
        minDist=args.min_dist,
        param1=args.hough_param1,
        param2=args.hough_param2,
        minRadius=args.min_radius,
        maxRadius=args.max_radius,
    )
    if raw is None:
        return []

    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    candidates = []
    for x, y, r in np.round(raw[0]).astype(int):
        if not (args.min_radius <= r <= args.max_radius):
            continue
        # Optional crop exclusion, useful for map ornaments/title boxes.
        if args.ignore_bottom_fraction and y > img_bgr.shape[0] * (1.0 - args.ignore_bottom_fraction):
            continue

        yy, xx = np.ogrid[:img_bgr.shape[0], :img_bgr.shape[1]]
        disk = (xx - x) ** 2 + (yy - y) ** 2 <= max(4, r - 2) ** 2
        h = hsv[:, :, 0][disk]
        s = hsv[:, :, 1][disk]
        v = hsv[:, :, 2][disk]

        # Junction centers are yellow/cream. This rejects many texture false positives.
        yellowish = ((h >= args.node_h_min) & (h <= args.node_h_max) &
                     (s >= args.node_s_min) & (v >= args.node_v_min)).mean()
        if yellowish >= args.min_yellow_fraction:
            candidates.append((x, y, r))

    return merge_circles(candidates, min_dist=args.merge_dist)


def road_mask(img_bgr, args):
    """Segment the yellow taxi-road network."""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    lower = np.array([args.road_h_min, args.road_s_min, args.road_v_min], dtype=np.uint8)
    upper = np.array([args.road_h_max, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)

    # Close small gaps and remove tiny specks.
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)
    return mask


def build_graph(img_bgr, junctions, args):
    """
    Build edges by removing each circular node from the road mask.
    Each remaining connected yellow component is a road segment; the nodes
    touching that segment become neighbors in the graph.
    """
    mask = road_mask(img_bgr, args)

    # Remove junction interiors so road segments between them become components.
    cut = mask.copy()
    for x, y, r in junctions:
        cv2.circle(cut, (x, y), int(r + args.node_cut_pad), 0, -1)

    # Skeletonization makes thick roads thinner and reduces accidental broad contacts.
    skel = skeletonize(cut > 0).astype(np.uint8) * 255
    skel = cv2.dilate(skel, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)

    nlabels, labels, stats, _ = cv2.connectedComponentsWithStats(skel, connectivity=8)
    G = nx.Graph()
    for idx, (x, y, r) in enumerate(junctions, start=1):
        G.add_node(idx, x=int(x), y=int(y), r=int(r))

    for comp_id in range(1, nlabels):
        area = stats[comp_id, cv2.CC_STAT_AREA]
        if area < args.min_segment_pixels:
            continue
        comp = (labels == comp_id).astype(np.uint8) * 255
        comp = cv2.dilate(comp, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (args.touch_dilate, args.touch_dilate)), iterations=1)

        touched = []
        for idx, (x, y, r) in enumerate(junctions, start=1):
            ring = np.zeros(comp.shape, dtype=np.uint8)
            cv2.circle(ring, (x, y), int(r + args.touch_radius_pad), 255, -1)
            if cv2.countNonZero(cv2.bitwise_and(comp, ring)) > 0:
                touched.append(idx)

        # Usually touched has exactly two nodes. If a road component touches more,
        # connect nearest pairs within that component to avoid a complete clique.
        if len(touched) == 2:
            G.add_edge(touched[0], touched[1])
        elif len(touched) > 2:
            pts = {i: np.array([junctions[i - 1][0], junctions[i - 1][1]]) for i in touched}
            for i in touched:
                ds = sorted((np.linalg.norm(pts[i] - pts[j]), j) for j in touched if j != i)
                for _, j in ds[:2]:
                    G.add_edge(i, j)
    return G


def write_outputs(img_bgr, junctions, G, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)

    labelled = img_bgr.copy()
    for idx, (x, y, r) in enumerate(junctions, start=1):
        label = str(idx)
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.42 if len(label) < 3 else 0.34
        thickness = 1
        (tw, th), _ = cv2.getTextSize(label, font, scale, thickness)
        # Text only: no edge/connection lines. A tiny light backing improves readability.
        cv2.circle(labelled, (x, y), max(8, r - 2), (245, 225, 160), -1)
        cv2.putText(labelled, label, (x - tw // 2, y + th // 2), font, scale, (20, 20, 20), thickness, cv2.LINE_AA)
    cv2.imwrite(str(out_dir / "junctions_labelled.png"), labelled)

    with open(out_dir / "junctions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "x", "y", "radius", "neighbors"])
        for idx, (x, y, r) in enumerate(junctions, start=1):
            w.writerow([idx, x, y, r, " ".join(map(str, sorted(G.neighbors(idx))))])

    graph_json = {
        "nodes": [{"id": i, **G.nodes[i]} for i in G.nodes],
        "edges": [{"source": int(a), "target": int(b)} for a, b in sorted(G.edges)],
        "adjacency": {str(i): sorted(map(int, G.neighbors(i))) for i in G.nodes},
    }
    with open(out_dir / "graph.json", "w", encoding="utf-8") as f:
        json.dump(graph_json, f, indent=2)

    nx.write_graphml(G, out_dir / "graph.graphml")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--image", required=True, help="Input map image, e.g. Taxi.png")
    p.add_argument("--out", default="taxi_cv_out", help="Output folder")

    # Circle detection parameters.
    p.add_argument("--min-radius", type=int, default=8)
    p.add_argument("--max-radius", type=int, default=18, help="Raise to include larger circles; lower to exclude ornaments/stations")
    p.add_argument("--min-dist", type=int, default=22)
    p.add_argument("--merge-dist", type=int, default=14)
    p.add_argument("--hough-dp", type=float, default=1.2)
    p.add_argument("--hough-param1", type=float, default=100)
    p.add_argument("--hough-param2", type=float, default=30, help="Lower detects more circles; higher detects fewer")
    p.add_argument("--ignore-bottom-fraction", type=float, default=0.06, help="Ignore detections in bottom ornament strip; set 0 to disable")
    p.add_argument("--node-h-min", type=int, default=12)
    p.add_argument("--node-h-max", type=int, default=38)
    p.add_argument("--node-s-min", type=int, default=35)
    p.add_argument("--node-v-min", type=int, default=135)
    p.add_argument("--min-yellow-fraction", type=float, default=0.35)

    # Road segmentation / connection parameters.
    p.add_argument("--road-h-min", type=int, default=10)
    p.add_argument("--road-h-max", type=int, default=42)
    p.add_argument("--road-s-min", type=int, default=35)
    p.add_argument("--road-v-min", type=int, default=130)
    p.add_argument("--node-cut-pad", type=int, default=5)
    p.add_argument("--touch-radius-pad", type=int, default=9)
    p.add_argument("--touch-dilate", type=int, default=7)
    p.add_argument("--min-segment-pixels", type=int, default=20)
    args = p.parse_args()

    img = cv2.imread(args.image)
    if img is None:
        raise SystemExit(f"Could not read image: {args.image}")

    junctions = detect_junctions(img, args)
    G = build_graph(img, junctions, args)
    write_outputs(img, junctions, G, Path(args.out))

    print(f"Detected junctions: {len(junctions)}")
    print(f"Detected edges: {G.number_of_edges()}")
    print(f"Outputs written to: {Path(args.out).resolve()}")
    print("Query example: open graph.json and read adjacency['1'], or use NetworkX: list(G.neighbors(1)).")


if __name__ == "__main__":
    main()
