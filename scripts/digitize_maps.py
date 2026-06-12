#!/usr/bin/env python3
"""
Multi-map digitizer for Scotland Yard.
Aligns Bus, Subway, and Map images to Taxi.png, projects the 153 master junctions,
snaps them to local circle centroids, builds transport graphs for each type, and writes outputs.
"""

import argparse
import csv
import json
import math
from pathlib import Path
import cv2
import networkx as nx
import numpy as np
from skimage.morphology import skeletonize

class DigitizerArgs:
    # Circle snapping settings
    node_h_min = 10
    node_h_max = 42
    node_s_min = 25
    node_v_min = 110
    
    # Road segmentation / connection parameters
    # Taxi Yellow mask
    taxi_h_min = 10
    taxi_h_max = 42
    taxi_s_min = 35
    taxi_v_min = 130
    
    # Bus Green mask
    bus_h_min = 35
    bus_h_max = 85
    bus_s_min = 40
    bus_v_min = 40
    
    # Subway Red mask
    sub_h_min = 0
    sub_h_max = 12
    sub_h_min_wrap = 160
    sub_h_max_wrap = 180
    sub_s_min = 50
    sub_v_min = 50
    
    # Connection parameters
    node_cut_pad = 5
    touch_radius_pad = 9
    touch_dilate = 7
    min_segment_pixels = 20

def load_master_junctions(csv_path):
    """Load reference coordinates from junctions.csv."""
    junctions = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        header = next(r)
        for row in r:
            if not row:
                continue
            jid, x, y, radius = int(row[0]), int(row[1]), int(row[2]), int(row[3])
            junctions.append((jid, x, y, radius))
    # Sort by ID to ensure consistency
    junctions.sort(key=lambda item: item[0])
    return junctions

def compute_homography(ref_img, tgt_img):
    """Compute Homography matrix mapping ref_img coordinates to tgt_img using ORB."""
    ref_gray = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
    tgt_gray = cv2.cvtColor(tgt_img, cv2.COLOR_BGR2GRAY)
    
    orb = cv2.ORB_create(nfeatures=5000)
    kp_ref, des_ref = orb.detectAndCompute(ref_gray, None)
    kp_tgt, des_tgt = orb.detectAndCompute(tgt_gray, None)
    
    if des_ref is None or des_tgt is None:
        print("Warning: ORB descriptors are empty. Using identity matrix.")
        return np.eye(3, dtype=np.float32)
        
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(des_ref, des_tgt)
    matches = sorted(matches, key=lambda x: x.distance)
    
    if len(matches) < 10:
        print("Warning: Too few matches found. Using identity matrix.")
        return np.eye(3, dtype=np.float32)
        
    points_ref = np.zeros((len(matches), 2), dtype=np.float32)
    points_tgt = np.zeros((len(matches), 2), dtype=np.float32)
    for i, m in enumerate(matches):
        points_ref[i, :] = kp_ref[m.queryIdx].pt
        points_tgt[i, :] = kp_tgt[m.trainIdx].pt
        
    h, mask = cv2.findHomography(points_ref, points_tgt, cv2.RANSAC, 5.0)
    if h is None:
        print("Warning: Homography estimation failed. Using identity matrix.")
        return np.eye(3, dtype=np.float32)
    return h

def snap_coordinate(img_bgr, x, y, search_r=20, args=DigitizerArgs):
    """Find the local yellowish/cream circle centroid and snap coordinates to it."""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    h, w = img_bgr.shape[:2]
    
    x_start = max(0, int(x - search_r))
    x_end = min(w, int(x + search_r + 1))
    y_start = max(0, int(y - search_r))
    y_end = min(h, int(y + search_r + 1))
    
    crop_hsv = hsv[y_start:y_end, x_start:x_end]
    
    # Mask for yellow/cream circle color
    mask = (crop_hsv[:, :, 0] >= args.node_h_min) & (crop_hsv[:, :, 0] <= args.node_h_max) & \
           (crop_hsv[:, :, 1] >= args.node_s_min) & (crop_hsv[:, :, 2] >= args.node_v_min)
           
    if np.sum(mask) == 0:
        return int(round(x)), int(round(y))
        
    nlabels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
    if nlabels <= 1:
        return int(round(x)), int(round(y))
        
    # Find centroid closest to the center of the crop
    crop_center_y = (y_end - y_start) / 2.0
    crop_center_x = (x_end - x_start) / 2.0
    best_dist = float('inf')
    best_cx, best_cy = x, y
    
    for i in range(1, nlabels):
        cx, cy = centroids[i]
        dist = math.hypot(cx - crop_center_x, cy - crop_center_y)
        if dist < best_dist:
            best_dist = dist
            best_cx = x_start + cx
            best_cy = y_start + cy
            
    return int(round(best_cx)), int(round(best_cy))

def segment_roads(img_bgr, mode, args=DigitizerArgs):
    """Segment roads using color thresholding based on the map mode."""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    
    if mode == "taxi":
        lower = np.array([args.taxi_h_min, args.taxi_s_min, args.taxi_v_min], dtype=np.uint8)
        upper = np.array([args.taxi_h_max, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
    elif mode == "bus":
        lower = np.array([args.bus_h_min, args.bus_s_min, args.bus_v_min], dtype=np.uint8)
        upper = np.array([args.bus_h_max, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
    elif mode == "subway":
        lower1 = np.array([args.sub_h_min, args.sub_s_min, args.sub_v_min], dtype=np.uint8)
        upper1 = np.array([args.sub_h_max, 255, 255], dtype=np.uint8)
        mask1 = cv2.inRange(hsv, lower1, upper1)
        
        lower2 = np.array([args.sub_h_min_wrap, args.sub_s_min, args.sub_v_min], dtype=np.uint8)
        upper2 = np.array([args.sub_h_max_wrap, 255, 255], dtype=np.uint8)
        mask2 = cv2.inRange(hsv, lower2, upper2)
        
        mask = cv2.bitwise_or(mask1, mask2)
    else:
        # Default to empty mask for other modes
        mask = np.zeros(img_bgr.shape[:2], dtype=np.uint8)
        
    # Morphological clean up
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)
    return mask

def build_graph(img_bgr, junctions, mode, args=DigitizerArgs):
    """Build graph edges by skeletonizing road mask and checking connectivity."""
    mask = segment_roads(img_bgr, mode, args)
    
    # Remove junction interiors so roads are disconnected components
    cut = mask.copy()
    for jid, x, y, r in junctions:
        cv2.circle(cut, (x, y), int(r + args.node_cut_pad), 0, -1)
        
    # Skeletonization
    skel = skeletonize(cut > 0).astype(np.uint8) * 255
    skel = cv2.dilate(skel, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
    
    nlabels, labels, stats, _ = cv2.connectedComponentsWithStats(skel, connectivity=8)
    G = nx.Graph()
    for jid, x, y, r in junctions:
        G.add_node(jid, x=int(x), y=int(y), r=int(r))
        
    for comp_id in range(1, nlabels):
        area = stats[comp_id, cv2.CC_STAT_AREA]
        if area < args.min_segment_pixels:
            continue
            
        comp = (labels == comp_id).astype(np.uint8) * 255
        comp = cv2.dilate(comp, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (args.touch_dilate, args.touch_dilate)), iterations=1)
        
        touched = []
        for jid, x, y, r in junctions:
            ring = np.zeros(comp.shape, dtype=np.uint8)
            cv2.circle(ring, (x, y), int(r + args.touch_radius_pad), 255, -1)
            if cv2.countNonZero(cv2.bitwise_and(comp, ring)) > 0:
                touched.append(jid)
                
        if len(touched) == 2:
            G.add_edge(touched[0], touched[1])
        elif len(touched) > 2:
            pts = {i: np.array([junctions[i - 1][1], junctions[i - 1][2]]) for i in touched}
            # Add edges between nearest pairs in the component
            for i in touched:
                ds = sorted((np.linalg.norm(pts[i] - pts[j]), j) for j in touched if j != i)
                for _, j in ds[:2]:
                    G.add_edge(i, j)
    return G

def write_outputs(img_bgr, junctions, G, out_dir):
    """Write labelled map image, junctions.csv, graph.json, and graph.graphml."""
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Label circles on the image
    labelled = img_bgr.copy()
    for jid, x, y, r in junctions:
        label = str(jid)
        font = cv2.FONT_HERSHEY_SIMPLEX
        # Use a slightly larger, highly readable scale for labels
        scale = 0.50 if len(label) < 3 else 0.40
        thickness = 1
        (tw, th), _ = cv2.getTextSize(label, font, scale, thickness)
        
        # Compute dynamic radius:
        # 1. Base radius has +3 padding to cover the circle on the map fully.
        # 2. Text radius is the distance from center to corners to keep the text inside the circle.
        text_radius = int(math.ceil(math.hypot(tw / 2.0, th / 2.0)))
        draw_r = max(r + 3, text_radius + 3)
        
        # Draw backing circle
        cv2.circle(labelled, (x, y), draw_r, (245, 225, 160), -1)
        # Draw text label centered
        cv2.putText(labelled, label, (x - tw // 2, y + th // 2), font, scale, (20, 20, 20), thickness, cv2.LINE_AA)
        
    cv2.imwrite(str(out_dir / "junctions_labelled.png"), labelled)
    
    # CSV file
    with open(out_dir / "junctions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "x", "y", "radius", "neighbors"])
        for jid, x, y, r in junctions:
            neighbors_str = " ".join(map(str, sorted(G.neighbors(jid))))
            w.writerow([jid, x, y, r, neighbors_str])
            
    # JSON file
    graph_json = {
        "nodes": [{"id": jid, **G.nodes[jid]} for jid in G.nodes],
        "edges": [{"source": int(a), "target": int(b)} for a, b in sorted(G.edges)],
        "adjacency": {str(jid): sorted(map(int, G.neighbors(jid))) for jid in G.nodes},
    }
    with open(out_dir / "graph.json", "w", encoding="utf-8") as f:
        json.dump(graph_json, f, indent=2)
        
    # GraphML file
    nx.write_graphml(G, out_dir / "graph.graphml")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--maps-dir", default=".", help="Directory containing Taxi.png, Bus.png, Subway.png, Map.png")
    args = p.parse_args()
    
    maps_dir = Path(args.maps_dir)
    
    # Find junctions.csv reference
    ref_csv_paths = [
        maps_dir / "taxi_cv_out" / "taxi_cv_out" / "junctions.csv",
        maps_dir / "taxi_cv_out" / "junctions.csv",
        maps_dir / "junctions.csv"
    ]
    csv_path = None
    for p_path in ref_csv_paths:
        if p_path.exists():
            csv_path = p_path
            break
            
    if not csv_path:
        raise SystemExit("Error: Could not find reference junctions.csv in taxi_cv_out folders or maps-dir.")
        
    print(f"Loading master junctions from: {csv_path}")
    master_juncs = load_master_junctions(csv_path)
    print(f"Loaded {len(master_juncs)} reference junctions.")
    
    # Load reference Taxi image
    taxi_img_path = maps_dir / "Taxi.png"
    if not taxi_img_path.exists():
        raise SystemExit(f"Error: {taxi_img_path} not found.")
    ref_img = cv2.imread(str(taxi_img_path))
    
    # Definitions of target maps
    targets = [
        {"name": "Taxi.png", "mode": "taxi", "out": "taxi_cv_out"},
        {"name": "Bus.png", "mode": "bus", "out": "bus_cv_out"},
        {"name": "Subway.png", "mode": "subway", "out": "subway_cv_out"},
        {"name": "Map.png", "mode": "map", "out": "map_cv_out"},
    ]
    
    # We will build and store graphs to merge them for the main Map
    graphs = {}
    snapped_junctions_dict = {}
    
    for tgt in targets:
        name = tgt["name"]
        mode = tgt["mode"]
        out_folder = maps_dir / tgt["out"]
        img_path = maps_dir / name
        
        if not img_path.exists():
            print(f"Skipping {name} (file not found).")
            continue
            
        print(f"\nProcessing {name} (mode={mode})...")
        img = cv2.imread(str(img_path))
        
        # 1. Coordinate alignment & snapping
        if name == "Taxi.png":
            # For reference map, we can use coordinates directly
            # Or snap to ensure they are perfectly centered on local yellow nodes
            snapped = []
            for jid, tx, ty, tr in master_juncs:
                sx, sy = snap_coordinate(img, tx, ty)
                snapped.append((jid, sx, sy, tr))
        else:
            # Align using homography relative to Taxi.png
            h = compute_homography(ref_img, img)
            snapped = []
            for jid, tx, ty, tr in master_juncs:
                pt = np.array([tx, ty], dtype=np.float32).reshape(1, 1, 2)
                mpt = cv2.perspectiveTransform(pt, h).reshape(2)
                sx, sy = snap_coordinate(img, mpt[0], mpt[1])
                snapped.append((jid, sx, sy, tr))
                
        snapped_junctions_dict[mode] = snapped
        print(f"  Mapped and snapped {len(snapped)} junctions.")
        
        # 2. Build graph (for Taxi, Bus, Subway)
        if mode != "map":
            G = build_graph(img, snapped, mode)
            graphs[mode] = G
            print(f"  Graph constructed: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")
            write_outputs(img, snapped, G, out_folder)
            print(f"  Outputs saved to: {out_folder}")
        else:
            # Map.png combined graph is the union of Taxi, Bus, Subway graphs
            G_map = nx.Graph()
            
            # Add nodes using the Map.png snapped coordinates
            for jid, x, y, r in snapped:
                G_map.add_node(jid, x=int(x), y=int(y), r=int(r))
                
            # Add edges from all transport graphs
            edge_count = 0
            for g_mode, G_transport in graphs.items():
                for u, v in G_transport.edges():
                    if not G_map.has_edge(u, v):
                        G_map.add_edge(u, v)
                        edge_count += 1
                        
            graphs["map"] = G_map
            print(f"  Map graph merged: {G_map.number_of_nodes()} nodes, {G_map.number_of_edges()} edges (union of taxi/bus/subway).")
            write_outputs(img, snapped, G_map, out_folder)
            print(f"  Outputs saved to: {out_folder}")
            
    print("\nDigitization complete!")

if __name__ == "__main__":
    main()
