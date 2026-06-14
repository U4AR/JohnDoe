from __future__ import annotations

import copy
import json
import random
import re
from dataclasses import asdict
from typing import Any

from config import load_settings
from grid_map.atlas import places_for_junction, primary_place_for_junction
from grid_map.graph_loader import legal_moves_from
from llm.omni_client import OmniClient

from .context_budget import ContextBudget, trim_text_to_tokens
from .culprit_engine import choose_rule_based_move
from .state import (
    CaseLandmark,
    CulpritMove,
    GameState,
    ObservableFact,
    PotentialWitness,
    StorySegment,
)


VENUE_TEMPLATES = {
    "market": [("secondhand_clothes", "Secondhand Clothes Stall", "thrift shop"), ("tea_counter", "Tea Counter", "cafe")],
    "street": [("phone_booth", "Public Telephone Booth", "phone booth"), ("news_kiosk", "Evening News Kiosk", "kiosk")],
    "square": [("taxi_rank", "Taxi Rank", "taxi rank"), ("corner_cafe", "Corner Cafe", "cafe")],
    "park": [("park_shelter", "Park Shelter", "shelter")],
    "waterfront": [("dock_cafe", "Dockworkers' Cafe", "cafe"), ("ticket_office", "Ferry Ticket Office", "ticket office")],
    "industrial": [("workwear_shop", "Workwear Store", "clothing shop")],
}

WITNESS_NAMES = [
    ("Eleanor Price", "shop assistant", "careful"),
    ("Arthur Bell", "cab driver", "blunt"),
    ("Mabel Finch", "telephone operator", "talkative"),
    ("Thomas Reed", "porter", "nervous"),
    ("Clara Shaw", "cafe owner", "observant"),
    ("George Vale", "newspaper seller", "skeptical"),
]

CRIME_TEMPLATES = [
    {
        "case_title": "The Midnight Star Affair",
        "crime": "theft of the Midnight Star diamond",
        "stolen_item": "the Midnight Star, a rare blue diamond",
        "victim": "the Ashcroft Collection",
        "scene": "a locked exhibition room",
        "detail": "The display glass was cut cleanly, but the alarm wire had been replaced with a length of black thread.",
    },
    {
        "case_title": "The Vanishing Crown",
        "crime": "theft of a royal coronation miniature",
        "stolen_item": "a jewel-encrusted coronation miniature",
        "victim": "the Royal Antiquities Society",
        "scene": "a guarded archive",
        "detail": "A cup of untouched tea and a forged curator's pass were the only things left behind.",
    },
    {
        "case_title": "The Black Ledger Job",
        "crime": "burglary of a private banking ledger",
        "stolen_item": "a coded ledger naming the city's secret creditors",
        "victim": "Bramwell & Finch Bank",
        "scene": "the basement records vault",
        "detail": "The vault remained locked; someone had removed the ledger through a narrow ventilation grille.",
    },
    {
        "case_title": "The Clockmaker's Ransom",
        "crime": "theft of an experimental gold chronometer",
        "stolen_item": "the only working Halden chronometer",
        "victim": "master clockmaker Elias Halden",
        "scene": "a workshop above Bellmaker Lane",
        "detail": "Every clock in the workshop had been stopped at precisely 11:47.",
    },
]


def initialize_case_story(state: GameState, use_model: bool = False) -> None:
    ensure_case_introduction(state, use_model=use_model)
    place = primary_place_for_junction(state.culprit.current_junction)
    place_name = place["name"] if place else f"Junction {state.culprit.current_junction}"
    fact = ObservableFact(
        fact_id="fact_t001_opening",
        turn_number=1,
        junction_id=state.culprit.current_junction,
        kind="last_seen",
        text=f"A person matching {state.initial_description} was last seen near {place_name}.",
        tags=_tags(state.initial_description, place_name, "last seen"),
        place_id=place.get("id") if place else None,
    )
    segment = StorySegment(
        segment_id="story_t001_opening",
        turn_number=1,
        from_junction=state.culprit.current_junction,
        to_junction=state.culprit.current_junction,
        mode="remain",
        route=[state.culprit.current_junction],
        changed_disguise=False,
        previous_disguise=state.initial_description,
        new_disguise=state.initial_description,
        narrative=f"{state.case_introduction['culprit_alias']} entered the case near {place_name}, dressed as last reported: {state.initial_description}",
        observable_facts=[fact],
        context_profile=_context_profile(),
    )
    state.story_segments.append(segment)
    state.story_memory.recent_segment_ids.append(segment.segment_id)
    state.story_memory.permanent_facts.append(fact.text)
    state.potential_witnesses.extend(_derive_witnesses(state, segment, use_model=use_model))


def ensure_case_introduction(state: GameState, use_model: bool = False) -> bool:
    if state.case_introduction:
        return False
    state.case_introduction = _create_case_introduction(state, use_model=use_model)
    return True


def _create_case_introduction(state: GameState, use_model: bool) -> dict[str, Any]:
    current = state.culprit.current_junction
    rng = random.Random(f"{state.game_id}:{current}")
    template = rng.choice(CRIME_TEMPLATES)
    alias = rng.choice(["The Wraith", "Velvet Jack", "The Lantern Thief", "The Grey Fox", "The Night Clerk"])
    moves = legal_moves_from(current)
    nearby_ids = []
    for move in moves:
        if move.destination not in nearby_ids:
            nearby_ids.append(move.destination)
        if len(nearby_ids) == 2:
            break
    trail_ids = [*reversed(nearby_ids), current]
    while len(trail_ids) < 3:
        trail_ids.insert(0, current)

    labels = ["Earlier report", "Possible escape route", "Last confirmed sighting"]
    details = [
        "A hurried figure was noticed shortly after the alarm was raised.",
        "A witness reported the suspect moving through the area without stopping.",
        f"The clearest sighting matches the description: {state.initial_description}",
    ]
    sightings = []
    for index, junction_id in enumerate(trail_ids[-3:]):
        place = primary_place_for_junction(junction_id)
        sightings.append({
            "label": labels[index],
            "junction_id": junction_id,
            "location": f"{place['name']} / Junction {junction_id}" if place else f"Junction {junction_id}",
            "detail": details[index],
            "confidence": ["unconfirmed", "probable", "confirmed"][index],
        })

    fallback = {
        **template,
        "culprit_alias": alias,
        "kicker": f"London wakes to the news that {template['stolen_item']} has vanished.",
        "narrative": (
            f"Before dawn, {alias} slipped into {template['scene']} and stole {template['stolen_item']} "
            f"from {template['victim']}. {template['detail']} By the time the constables arrived, the thief had "
            "already melted into the streets, leaving only a broken trail of sightings behind."
        ),
        "last_seen": sightings,
    }
    if not use_model:
        return fallback

    payload = {
        "crime_facts": template,
        "culprit_alias": alias,
        "suspect_description": state.initial_description,
        "public_sighting_trail": sightings,
    }
    system = (
        "Write a punchy, family-friendly noir opening for a detective board game. Return JSON only with "
        "case_title, kicker, narrative, culprit_alias, crime, stolen_item, victim. Preserve every supplied fact, "
        "alias, and location; do not add or remove sightings. Keep narrative under 110 words."
    )
    try:
        data = OmniClient.from_settings().json_chat(system, json.dumps(payload), task="story", temperature=0.7)
        intro = {**fallback}
        for key in ("case_title", "kicker", "narrative", "culprit_alias", "crime", "stolen_item", "victim"):
            value = str(data.get(key) or "").strip()
            if value:
                intro[key] = value
        intro["last_seen"] = sightings
        return intro
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def generate_turn_bundle(state: GameState, use_model: bool = False) -> tuple[CulpritMove, StorySegment, list[PotentialWitness], list[CaseLandmark]]:
    working = copy.deepcopy(state)
    move = _choose_decision(working, use_model=use_model)
    previous_disguise = working.culprit.current_disguise
    if move.changed_disguise and working.culprit.remaining_disguise_changes <= 0:
        raise ValueError("Model requested a disguise change when none remain.")
    story, venues = _create_story(working, move, previous_disguise, use_model=use_model)
    _validate_story_against_move(story, move)
    _ensure_route_facts(story)
    witnesses = _derive_witnesses(working, story, use_model=use_model)
    return move, story, witnesses, venues


def _ensure_route_facts(story: StorySegment) -> None:
    if story.from_junction == story.to_junction:
        return
    if any(fact.junction_id == story.from_junction for fact in story.observable_facts):
        return
    story.observable_facts.insert(0, ObservableFact(
        fact_id=f"fact_t{story.turn_number:03d}_departure",
        turn_number=story.turn_number,
        junction_id=story.from_junction,
        kind="departure",
        text=(
            f"A person matching {story.previous_disguise} left Junction {story.from_junction} "
            f"by {story.mode}."
        ),
        tags=_tags(story.previous_disguise, story.mode, "left", "departure"),
    ))


def apply_turn_bundle(
    state: GameState,
    move: CulpritMove,
    story: StorySegment,
    witnesses: list[PotentialWitness],
    venues: list[CaseLandmark],
) -> None:
    state.culprit.current_junction = move.to_junction
    state.culprit.route_history.append(move)
    if move.changed_disguise:
        state.culprit.current_disguise = story.new_disguise
        state.culprit.remaining_disguise_changes -= 1
    state.story_segments.append(story)
    state.case_landmarks.extend(venue for venue in venues if all(item.venue_id != venue.venue_id for item in state.case_landmarks))
    state.potential_witnesses.extend(witnesses)
    state.story_memory.recent_segment_ids.append(story.segment_id)
    for fact in story.observable_facts:
        state.story_memory.permanent_facts.append(fact.text)
    compact_story_memory(state)
    state.game_log.append({
        "turn_number": state.turn_number,
        "kind": "culprit_move_private",
        "message": f"Culprit moved from {move.from_junction} to {move.to_junction} by {move.mode}.",
    })


def compact_story_memory(state: GameState) -> None:
    budget = ContextBudget.for_context(state.effective_context_length)
    recent = state.story_segments[-budget.recent_story_segments :]
    state.story_memory.recent_segment_ids = [segment.segment_id for segment in recent]
    older = state.story_segments[: -budget.recent_story_segments]
    if older:
        summary_lines = [
            f"T{s.turn_number}: J{s.from_junction} to J{s.to_junction} by {s.mode}; disguise: {s.new_disguise}."
            for s in older
        ]
        combined = " ".join(summary_lines)
        state.story_memory.continuity_synopsis = trim_text_to_tokens(combined, budget.synopsis_tokens)


def story_reveal(state: GameState) -> dict[str, Any]:
    return {
        "game_id": state.game_id,
        "result": state.result,
        "finalized_reason": state.finalized_reason,
        "initial_description": state.initial_description,
        "segments": [asdict(segment) for segment in state.story_segments],
        "case_landmarks": [asdict(landmark) for landmark in state.case_landmarks],
    }


def _choose_decision(state: GameState, use_model: bool) -> CulpritMove:
    fallback = choose_rule_based_move(state)
    if not use_model:
        return _maybe_change_disguise(state, fallback)
    moves = [move for move in legal_moves_from(state.culprit.current_junction, [asdict(block) for block in state.active_blocks]) if not move.blocked]
    if not moves:
        return fallback
    prompt = {
        "current_junction": state.culprit.current_junction,
        "current_disguise": state.culprit.current_disguise,
        "remaining_disguise_changes": state.culprit.remaining_disguise_changes,
        "legal_moves": [{"destination": m.destination, "mode": m.mode, "route": list(m.via)} for m in moves],
        "recent_police_attention": [entry for entry in state.game_log[-8:] if entry.get("kind") != "culprit_move_private"],
        "continuity_facts": state.story_memory.permanent_facts[-12:],
    }
    system = "Choose exactly one supplied legal move. Optionally change disguise. Return JSON only: destination, mode, route, change_disguise, new_disguise, risk_level."
    last_error = ""
    for _ in range(2):
        request = json.dumps({**prompt, "previous_validation_error": last_error})
        try:
            data = OmniClient.from_settings().json_chat(system, request, task="decision", temperature=0.25)
            return _validated_decision(state, moves, data)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)
    return _maybe_change_disguise(state, fallback)


def _validated_decision(state: GameState, moves: list[Any], data: dict[str, Any]) -> CulpritMove:
    if "destination" in data and "mode" in data:
        destination = int(data["destination"])
        mode = str(data["mode"])
    else:
        action = str(data.get("action") or "").lower()
        match = re.search(r"\b(bus|taxi|subway|walk|foot)\b\D+(\d+)\b", action)
        if not match:
            raise ValueError("Decision must include destination and mode.")
        mode = "walk" if match.group(1) == "foot" else match.group(1)
        destination = int(match.group(2))
    chosen = next((move for move in moves if move.destination == destination and move.mode == mode), None)
    if chosen is None:
        raise ValueError("Destination and mode must match one supplied legal move.")
    change = bool(data.get("change_disguise"))
    new_disguise = str(data.get("new_disguise") or "").strip()
    if change and (not new_disguise or state.culprit.remaining_disguise_changes <= 0):
        raise ValueError("Disguise change is unavailable or missing a new disguise.")
    move = CulpritMove(
        turn_number=state.turn_number,
        from_junction=state.culprit.current_junction,
        to_junction=destination,
        mode=mode,
        route=list(chosen.via),
        changed_disguise=change,
        risk_level=str(data.get("risk_level") or "unknown"),
    )
    setattr(move, "proposed_disguise", new_disguise)
    if change:
        _force_stationary(move, state.culprit.current_junction)
    return move


def _maybe_change_disguise(state: GameState, move: CulpritMove) -> CulpritMove:
    if state.culprit.remaining_disguise_changes and state.turn_number % 4 == 0:
        move.changed_disguise = True
        setattr(move, "proposed_disguise", "a brown leather jacket over dark trousers, carrying no visible folder")
        _force_stationary(move, state.culprit.current_junction)
    return move


def _force_stationary(move: CulpritMove, current_junction: int) -> None:
    move.to_junction = current_junction
    move.from_junction = current_junction
    move.mode = "remain"
    move.route = [current_junction]


def _create_story(state: GameState, move: CulpritMove, previous_disguise: str, use_model: bool) -> tuple[StorySegment, list[CaseLandmark]]:
    place = primary_place_for_junction(move.to_junction)
    venue = _ensure_subvenue(state, move.to_junction, place, move.changed_disguise)
    venues = [venue] if venue else []
    proposed = getattr(move, "proposed_disguise", "")
    new_disguise = proposed if move.changed_disguise else previous_disguise
    if not use_model:
        return _deterministic_story(state, move, previous_disguise, new_disguise, place, venue), venues

    payload = {
        "immutable_decision": {
            "from_junction": move.from_junction,
            "to_junction": move.to_junction,
            "mode": move.mode,
            "route": move.route,
            "changed_disguise": move.changed_disguise,
            "new_disguise": new_disguise,
        },
        "canonical_places": places_for_junction(move.to_junction),
        "case_subvenue": asdict(venue) if venue else None,
        "continuity_synopsis": state.story_memory.continuity_synopsis,
        "recent_story": [segment.narrative for segment in state.story_segments[-ContextBudget.for_context(state.effective_context_length).recent_story_segments :]],
    }
    system = "Write the next hidden John Doe story around the immutable decision. Return JSON only: narrative, private_reasoning, observable_facts[{kind,text,tags,place_id}]. Never change route, mode, destination, or disguise."
    try:
        data = OmniClient.from_settings().json_chat(system, json.dumps(payload), task="story", temperature=0.55)
        facts = _facts_from_model(state, move, data.get("observable_facts", []))
        narrative = str(data["narrative"])
        private_reasoning = str(data.get("private_reasoning", ""))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _deterministic_story(state, move, previous_disguise, new_disguise, place, venue), venues
    story = StorySegment(
        segment_id=f"story_t{state.turn_number:03d}", turn_number=state.turn_number,
        from_junction=move.from_junction, to_junction=move.to_junction, mode=move.mode, route=move.route,
        changed_disguise=move.changed_disguise, previous_disguise=previous_disguise, new_disguise=new_disguise,
        narrative=narrative, private_reasoning=private_reasoning,
        observable_facts=facts, context_profile=_context_profile(),
    )
    return story, venues


def _deterministic_story(state: GameState, move: CulpritMove, previous: str, new: str, place: dict[str, Any] | None, venue: CaseLandmark | None) -> StorySegment:
    place_name = place["name"] if place else f"Junction {move.to_junction}"
    venue_name = venue.name if venue else place_name
    stationary = move.from_junction == move.to_junction
    if stationary:
        action = f"John Doe stayed at {place_name} near Junction {move.to_junction} this turn."
    else:
        action = f"John Doe travelled by {move.mode} from Junction {move.from_junction} to {place_name} at Junction {move.to_junction}."
    facts = [ObservableFact(
        fact_id=f"fact_t{state.turn_number:03d}_001", turn_number=state.turn_number,
        junction_id=move.to_junction, kind="movement" if not stationary else "lingered",
        text=(
            f"A person matching {previous} was seen lingering near {place_name}."
            if stationary
            else f"A person matching {previous} arrived near {place_name} by {move.mode}."
        ),
        tags=_tags(previous, place_name, move.mode if not stationary else "lingered", "arrived" if not stationary else "lingered"),
        place_id=place.get("id") if place else None,
    )]
    if move.changed_disguise:
        action += f" At {venue_name}, he replaced his visible clothing and emerged wearing {new}."
        facts.append(ObservableFact(
            fact_id=f"fact_t{state.turn_number:03d}_002", turn_number=state.turn_number,
            junction_id=move.to_junction, kind="disguise_change",
            text=f"A person entered {venue_name} dressed as {previous} and later emerged wearing {new}.",
            tags=_tags(previous, new, venue_name, "clothing", "changed"), place_id=venue.venue_id if venue else None,
        ))
    return StorySegment(
        segment_id=f"story_t{state.turn_number:03d}", turn_number=state.turn_number,
        from_junction=move.from_junction, to_junction=move.to_junction, mode=move.mode, route=move.route,
        changed_disguise=move.changed_disguise, previous_disguise=previous, new_disguise=new,
        narrative=action, private_reasoning="He chose the route to reduce police attention.",
        observable_facts=facts, context_profile=_context_profile(),
    )


def _derive_witnesses(state: GameState, story: StorySegment, use_model: bool) -> list[PotentialWitness]:
    witnesses: list[PotentialWitness] = []
    for index, fact in enumerate(story.observable_facts):
        name, occupation, style = WITNESS_NAMES[(len(state.potential_witnesses) + index) % len(WITNESS_NAMES)]
        witnesses.append(PotentialWitness(
            potential_id=f"potential_{fact.fact_id}_{index + 1}", turn_created=story.turn_number,
            junction_id=fact.junction_id, observed_fact_ids=[fact.fact_id],
            profile={"name": name, "occupation": occupation, "style": style, "confidence": "measured"},
            reliability=round(0.58 + (index % 4) * 0.09, 2), memory_strength=round(0.62 + (index % 3) * 0.08, 2),
            voice_id=f"voice_{((len(state.potential_witnesses) + index) % 6) + 1:02d}", summary=fact.text,
            search_tags=fact.tags + [name.lower(), occupation.lower()],
        ))
        if fact.kind == "disguise_change":
            alt_name, alt_occupation, alt_style = WITNESS_NAMES[(len(state.potential_witnesses) + index + 2) % len(WITNESS_NAMES)]
            witnesses.append(PotentialWitness(
                potential_id=f"potential_{fact.fact_id}_nearby", turn_created=story.turn_number,
                junction_id=fact.junction_id, observed_fact_ids=[fact.fact_id],
                profile={"name": alt_name, "occupation": alt_occupation, "style": alt_style, "confidence": "uncertain"},
                reliability=0.54, memory_strength=0.68,
                voice_id=f"voice_{((len(state.potential_witnesses) + index + 2) % 6) + 1:02d}",
                summary=f"From nearby, {alt_name} noticed only part of this event: {fact.text}", search_tags=fact.tags,
            ))
    return witnesses


def _ensure_subvenue(state: GameState, junction_id: int, place: dict[str, Any] | None, needed: bool) -> CaseLandmark | None:
    existing = next((venue for venue in state.case_landmarks if venue.junction_id == junction_id), None)
    if existing:
        return existing
    category = (place or {}).get("category", "street")
    choices = VENUE_TEMPLATES.get(category, VENUE_TEMPLATES["street"])
    template_id, name, venue_category = choices[junction_id % len(choices)]
    if not needed and junction_id % 3:
        return None
    return CaseLandmark(
        venue_id=f"case_j{junction_id}_{template_id}", name=name, category=venue_category,
        junction_id=junction_id, canonical_place_id=(place or {}).get("id"),
        description=f"A case-specific {venue_category} near {(place or {}).get('name', f'Junction {junction_id}')}",
    )


def _facts_from_model(state: GameState, move: CulpritMove, raw_facts: list[dict[str, Any]]) -> list[ObservableFact]:
    facts: list[ObservableFact] = []
    for index, raw in enumerate(raw_facts[:6], start=1):
        facts.append(ObservableFact(
            fact_id=f"fact_t{state.turn_number:03d}_{index:03d}", turn_number=state.turn_number,
            junction_id=move.to_junction, kind=str(raw.get("kind") or "observation"),
            text=str(raw.get("text") or "").strip(), tags=[str(tag).lower() for tag in raw.get("tags", [])],
            place_id=raw.get("place_id"),
        ))
    if not facts or any(not fact.text for fact in facts):
        raise ValueError("Story must contain at least one non-empty observable fact.")
    return facts


def _validate_story_against_move(story: StorySegment, move: CulpritMove) -> None:
    if (story.from_junction, story.to_junction, story.mode, story.route, story.changed_disguise) != (
        move.from_junction, move.to_junction, move.mode, move.route, move.changed_disguise
    ):
        raise ValueError("Story output changed the immutable movement decision.")


def _context_profile() -> dict[str, Any]:
    settings = load_settings()
    budget = ContextBudget.for_context(settings.llamacpp_context_length)
    return {"context_length": budget.context_length, "output_tokens": budget.output_tokens, "prompt_tokens": budget.prompt_tokens}


def _tags(*values: str) -> list[str]:
    words: set[str] = set()
    for value in values:
        words.update(word.strip(".,:;!?()[]\"").lower() for word in value.split() if len(word) > 2)
    return sorted(words)
