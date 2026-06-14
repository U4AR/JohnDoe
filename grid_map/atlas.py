from __future__ import annotations

from typing import Any

from config import load_settings
from .graph_loader import all_junction_ids
from .storage import read_json


def load_map_atlas() -> dict[str, Any]:
    return read_json(load_settings().map_atlas_path)


def validate_map_atlas(atlas: dict[str, Any] | None = None) -> list[str]:
    atlas = atlas or load_map_atlas()
    valid_junctions = set(all_junction_ids())
    errors: list[str] = []
    district_ids: set[str] = set()
    landmark_ids: set[str] = set()

    for district in atlas.get("districts", []):
        district_id = str(district.get("id", "")).strip()
        if not district_id or district_id in district_ids:
            errors.append(f"Invalid or duplicate district id: {district_id!r}")
        district_ids.add(district_id)
        errors.extend(_junction_errors(district, valid_junctions, district_id))
        errors.extend(_anchor_errors(district, district_id))

    for landmark in atlas.get("landmarks", []):
        landmark_id = str(landmark.get("id", "")).strip()
        if not landmark_id or landmark_id in landmark_ids:
            errors.append(f"Invalid or duplicate landmark id: {landmark_id!r}")
        landmark_ids.add(landmark_id)
        district_id = landmark.get("district_id")
        if district_id and district_id not in district_ids:
            errors.append(f"Landmark {landmark_id} references unknown district {district_id}")
        errors.extend(_junction_errors(landmark, valid_junctions, landmark_id))
        errors.extend(_anchor_errors(landmark, landmark_id))
    return errors


def places_for_junction(junction_id: int) -> list[dict[str, Any]]:
    atlas = load_map_atlas()
    matches: list[dict[str, Any]] = []
    for entry in [*atlas.get("districts", []), *atlas.get("landmarks", [])]:
        junctions = set(entry.get("junction_ids", []))
        if entry.get("junction_id") is not None:
            junctions.add(entry["junction_id"])
        junctions.update(entry.get("nearby_junction_ids", []))
        if junction_id in junctions:
            matches.append(entry)
    return matches


def primary_place_for_junction(junction_id: int) -> dict[str, Any] | None:
    places = places_for_junction(junction_id)
    landmarks = [place for place in places if place.get("category") != "district"]
    return (landmarks or places or [None])[0]


def public_atlas_payload() -> dict[str, Any]:
    atlas = load_map_atlas()
    return {
        "schema_version": atlas.get("schema_version", 1),
        "map_id": atlas.get("map_id", "london_main"),
        "districts": atlas.get("districts", []),
        "landmarks": atlas.get("landmarks", []),
    }


def _junction_errors(entry: dict[str, Any], valid: set[int], entry_id: str) -> list[str]:
    values = list(entry.get("junction_ids", [])) + list(entry.get("nearby_junction_ids", []))
    if entry.get("junction_id") is not None:
        values.append(entry["junction_id"])
    return [f"{entry_id} references unknown junction {value}" for value in values if value not in valid]


def _anchor_errors(entry: dict[str, Any], entry_id: str) -> list[str]:
    anchor = entry.get("anchor") or {}
    x = anchor.get("x")
    y = anchor.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return [f"{entry_id} has an invalid anchor"]
    if not 0 <= x <= 1450 or not 0 <= y <= 1090:
        return [f"{entry_id} anchor is outside the map"]
    return []
