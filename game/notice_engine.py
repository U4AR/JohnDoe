from __future__ import annotations

import re

from grid_map.graph_loader import adjacent_junctions, all_junction_ids

from .state import GameState, LookoutNotice


GENERIC_WORDS = {
    "anyone",
    "someone",
    "suspicious",
    "nervous",
    "person",
    "people",
    "bag",
    "coat",
    "area",
    "nearby",
}

SPECIFIC_WORDS = {
    "raincoat",
    "folder",
    "red",
    "grey",
    "gray",
    "helmet",
    "backpack",
    "courier",
    "tan",
    "blue",
}


def create_lookout_notice(state: GameState, text: str, anchor_junction: int | None = None) -> LookoutNotice:
    notice_number = len(state.notices) + 1
    parsed = parse_notice(text, state, anchor_junction=anchor_junction)
    return LookoutNotice(
        notice_id=f"notice_{notice_number:03d}",
        turn_number=state.turn_number,
        text=text.strip(),
        parsed_location=parsed["parsed_location"],
        parsed_description=parsed["parsed_description"],
        genericness_score=parsed["genericness_score"],
        false_positive_likelihood=parsed["false_positive_likelihood"],
        response_plan=parsed["response_plan"],
    )


def parse_notice(text: str, state: GameState, anchor_junction: int | None = None) -> dict:
    clean = " ".join(text.strip().split())
    lowered = clean.lower()
    mentioned = [int(value) for value in re.findall(r"\bjunction\s*(\d+)\b|\bj\s*(\d+)\b", lowered) for value in value if value]
    if not mentioned:
        mentioned = [int(value) for value in re.findall(r"\b(\d{1,3})\b", lowered)]

    valid_ids = set(all_junction_ids())
    mentioned = [junction_id for junction_id in mentioned if junction_id in valid_ids]

    words = set(re.findall(r"[a-z]+", lowered))
    generic_hits = len(words & GENERIC_WORDS)
    specific_hits = len(words & SPECIFIC_WORDS)
    anchor = anchor_junction if anchor_junction in valid_ids else None
    has_location = bool(mentioned or anchor)

    if mentioned or anchor:
        anchors = list(dict.fromkeys([*([anchor] if anchor is not None else []), *mentioned[:3]]))
        relevant = _expand_junctions(anchors)
        parsed_location = ", ".join(f"Junction {junction_id}" for junction_id in anchors)
    elif any(word in lowered for word in ("all", "everyone", "city", "anywhere")):
        relevant = _citywide_sample(state.culprit.current_junction)
        parsed_location = "city-wide"
    else:
        relevant = _expand_junctions([state.culprit.current_junction])
        parsed_location = "near current public search area"

    genericness = _clamp(0.55 + generic_hits * 0.12 - specific_hits * 0.10 - (0.18 if has_location else 0.0))
    false_positive = _clamp(0.35 + genericness * 0.55 - specific_hits * 0.04)
    response_plan = _response_plan(relevant, state, genericness, false_positive)
    return {
        "parsed_location": parsed_location,
        "parsed_description": clean,
        "genericness_score": round(genericness, 2),
        "false_positive_likelihood": round(false_positive, 2),
        "response_plan": response_plan,
    }


def _expand_junctions(junctions: list[int]) -> list[int]:
    expanded: list[int] = list(dict.fromkeys(junctions))
    for junction_id in junctions:
        for neighbor in adjacent_junctions(junction_id)[:4]:
            if neighbor not in expanded:
                expanded.append(neighbor)
    return expanded


def _citywide_sample(anchor: int) -> list[int]:
    ids = all_junction_ids()
    stride = max(len(ids) // 14, 1)
    sampled = ids[::stride][:14]
    if anchor not in sampled:
        sampled.append(anchor)
    return sorted(set(sampled))


def _response_plan(junctions: list[int], state: GameState, genericness: float, false_positive: float) -> list[dict]:
    plan: list[dict] = []
    culprit_junction = state.culprit.current_junction
    recent_route = {move.to_junction for move in state.culprit.route_history[-3:]}
    recent_route.add(culprit_junction)
    lookout_influence = _lookout_influence(state)

    for index, junction_id in enumerate(junctions):
        near_culprit = junction_id in recent_route
        base = 1 + int(genericness * 6)
        if index == 0:
            base += 2
        if near_culprit:
            base += 2
        if junction_id in lookout_influence:
            base += lookout_influence[junction_id]
        witnesses = max(1, base)
        relevance_bias = 0.18 + (0.55 if near_culprit else 0.0) + (0.18 * (1.0 - false_positive))
        if junction_id in lookout_influence:
            relevance_bias += 0.08
        plan.append(
            {
                "junction_id": junction_id,
                "estimated_witnesses": witnesses,
                "relevance_bias": round(_clamp(relevance_bias), 2),
            }
        )
    return plan


def _lookout_influence(state: GameState) -> dict[int, int]:
    influence: dict[int, int] = {}
    for tactic in state.placed_tactics:
        if tactic.tactic_type != "lookout_board":
            continue
        influence[tactic.junction_id] = max(influence.get(tactic.junction_id, 0), 3)
        for neighbor in adjacent_junctions(tactic.junction_id)[:4]:
            influence[neighbor] = max(influence.get(neighbor, 0), 1)
    return influence


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return min(max(value, minimum), maximum)
