from __future__ import annotations

import math
import os
import random
import subprocess
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any

import gradio as gr
from fastapi import HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import load_settings
from game.rules import checks_remaining_this_turn
from game.session import (
    TACTIC_LIMITS,
    add_block,
    check_junction,
    end_turn,
    issue_notice,
    new_game,
    place_tactic,
    question_witness,
    remove_tactic,
)
from game.state import GameState
from grid_map.graph_loader import all_junction_ids, legal_moves_from
from grid_map.map_loader import image_for_layer, load_map_metadata
from grid_map.storage import read_json

DEFAULT_DESCRIPTION = "A nervous-looking person in a grey raincoat carrying a red folder."
DEFAULT_NOTICE = "Request high-confidence reports of a grey raincoat carrying a red folder at the selected junction."
DEFAULT_QUESTION = "What exactly did the person carry?"
DEFAULT_SELECTED_JUNCTION = 100
MAP_CLICK_RADIUS = 64

PROJECT_ROOT = Path(__file__).resolve().parent
WEB_DIR = PROJECT_ROOT / "ui" / "web"
STATIC_DIR = WEB_DIR / "static"

_SESSIONS: dict[str, GameState] = {}
_LLAMA_PROCESS: subprocess.Popen | None = None

DIFFICULTY_PRESETS = {
    "easy": {"PHANTOM_GRID_MAX_TURNS": "16", "PHANTOM_GRID_CHECKS_PER_TURN": "3", "PHANTOM_GRID_MEMORY_CORRUPTION_PER_TURN": "0.04"},
    "normal": {"PHANTOM_GRID_MAX_TURNS": "12", "PHANTOM_GRID_CHECKS_PER_TURN": "2", "PHANTOM_GRID_MEMORY_CORRUPTION_PER_TURN": "0.08"},
    "hard": {"PHANTOM_GRID_MAX_TURNS": "10", "PHANTOM_GRID_CHECKS_PER_TURN": "1", "PHANTOM_GRID_MEMORY_CORRUPTION_PER_TURN": "0.12"},
}


def build_app() -> gr.Server:
    app = gr.Server()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def homepage() -> str:
        return (WEB_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/assets/maps/{layer}")
    async def map_asset(layer: str) -> FileResponse:
        try:
            path = Path(image_for_layer(layer))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown map layer: {layer}") from exc
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Missing map asset: {layer}")
        return FileResponse(path)

    @app.get("/assets/suspect")
    async def suspect_asset() -> FileResponse:
        return FileResponse(STATIC_DIR / "default-suspect.svg", media_type="image/svg+xml")

    @app.get("/api/snapshot")
    async def snapshot_route(game_id: str | None = None) -> dict[str, Any]:
        return game_snapshot(game_id)

    @app.post("/api/new_case")
    async def new_case_route(payload: dict[str, Any]) -> dict[str, Any]:
        return new_case(payload.get("initial_description") or DEFAULT_DESCRIPTION)

    @app.post("/api/select_junctions")
    async def select_junctions_route(payload: dict[str, Any]) -> dict[str, Any]:
        return select_junctions(
            payload.get("game_id"),
            payload.get("selected_junctions") or [],
            payload.get("focused_junction"),
        )

    @app.post("/api/issue_notice")
    async def issue_notice_route(payload: dict[str, Any]) -> dict[str, Any]:
        return api_issue_notice(
            payload.get("game_id"),
            payload.get("notice_text") or DEFAULT_NOTICE,
            payload.get("selected_junctions") or [],
            payload.get("focused_junction"),
        )

    @app.post("/api/add_block")
    async def add_block_route(payload: dict[str, Any]) -> dict[str, Any]:
        return api_add_block(
            payload.get("game_id"),
            payload.get("block_type") or "junction_block",
            payload.get("focused_junction"),
            payload.get("to_junction"),
            payload.get("mode"),
            payload.get("turns") or 1,
            payload.get("selected_junctions") or [],
        )

    @app.post("/api/place_tactic")
    async def place_tactic_route(payload: dict[str, Any]) -> dict[str, Any]:
        return api_place_tactic(
            payload.get("game_id"),
            payload.get("tactic_type"),
            payload.get("junction_id"),
            payload.get("selected_junctions") or [],
            payload.get("focused_junction"),
        )

    @app.post("/api/remove_tactic")
    async def remove_tactic_route(payload: dict[str, Any]) -> dict[str, Any]:
        return api_remove_tactic(
            payload.get("game_id"),
            payload.get("tactic_id"),
            payload.get("selected_junctions") or [],
            payload.get("focused_junction"),
        )

    @app.post("/api/check_junctions")
    async def check_junctions_route(payload: dict[str, Any]) -> dict[str, Any]:
        return api_check_junctions(
            payload.get("game_id"),
            payload.get("selected_junctions") or [],
            payload.get("focused_junction"),
        )

    @app.post("/api/ask_witness")
    async def ask_witness_route(payload: dict[str, Any]) -> dict[str, Any]:
        return api_ask_witness(
            payload.get("game_id"),
            payload.get("witness_id"),
            payload.get("question") or DEFAULT_QUESTION,
            payload.get("selected_junctions") or [],
            payload.get("focused_junction"),
        )

    @app.post("/api/advance_turn")
    async def advance_turn_route(payload: dict[str, Any]) -> dict[str, Any]:
        return api_advance_turn(
            payload.get("game_id"),
            payload.get("selected_junctions") or [],
            payload.get("focused_junction"),
        )

    @app.get("/api/settings")
    async def settings_route() -> dict[str, Any]:
        return api_settings()

    @app.post("/api/settings")
    async def update_settings_route(payload: dict[str, Any]) -> dict[str, Any]:
        return api_update_settings(payload)

    @app.post("/api/llama/{action}")
    async def llama_action_route(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return api_llama_action(action, payload or {})

    app.api(new_case, name="new_case")
    app.api(select_junctions, name="select_junctions")
    app.api(api_issue_notice, name="issue_notice")
    app.api(api_add_block, name="add_block")
    app.api(api_place_tactic, name="place_tactic")
    app.api(api_remove_tactic, name="remove_tactic")
    app.api(api_check_junctions, name="check_junctions")
    app.api(api_ask_witness, name="ask_witness")
    app.api(api_advance_turn, name="advance_turn")
    app.api(game_snapshot, name="game_snapshot")
    return app


def new_case(initial_description: str = DEFAULT_DESCRIPTION) -> dict[str, Any]:
    state = new_game(initial_description or DEFAULT_DESCRIPTION)
    _SESSIONS[state.game_id] = state
    return _snapshot(
        state,
        selected_junctions=[],
        focused_junction=None,
        event="Case opened. The starting point is hidden.",
        sound="lookout_raise",
    )


def select_junctions(
    game_id: str | None = None,
    selected_junctions: list[int] | None = None,
    focused_junction: int | None = None,
) -> dict[str, Any]:
    state = _state_for(game_id, required=False)
    clean_selected = _valid_junctions(selected_junctions or [])
    clean_focused = _valid_junction(focused_junction) or (clean_selected[-1] if clean_selected else None)
    return _snapshot(
        state,
        selected_junctions=clean_selected,
        focused_junction=clean_focused,
        event=_selection_event(clean_selected, clean_focused),
        sound="map_select",
    )


def api_issue_notice(
    game_id: str | None,
    notice_text: str = DEFAULT_NOTICE,
    selected_junctions: list[int] | None = None,
    focused_junction: int | None = None,
) -> dict[str, Any]:
    state = _state_for(game_id)
    selected, focused = _selection_context(selected_junctions, focused_junction)
    if focused is None:
        focused = DEFAULT_SELECTED_JUNCTION
        selected = [focused]
    text = _notice_with_selected_junction(notice_text or DEFAULT_NOTICE, focused)
    state, batch = issue_notice(state, text)
    _SESSIONS[state.game_id] = state
    message = f"{batch.total_witnesses} witnesses surfaced."
    if batch.individual_review_allowed:
        message += " Witness cards are available."
    else:
        message += " The crowd is too dense for individual cards."
    return _snapshot(state, selected, focused, message, sound="witness_popup")


def api_add_block(
    game_id: str | None,
    block_type: str,
    focused_junction: int | None = None,
    to_junction: int | None = None,
    mode: str | None = None,
    turns: int = 1,
    selected_junctions: list[int] | None = None,
) -> dict[str, Any]:
    state = _state_for(game_id)
    selected, focused = _selection_context(selected_junctions, focused_junction)
    if focused is None:
        return _snapshot(state, selected, focused, "Select a junction before placing a blockade.", sound="map_select")

    if block_type == "edge_block":
        if _valid_junction(to_junction) is None:
            return _snapshot(state, selected, focused, "Pick a connected route first.", sound="map_select")
        state, message = add_block(
            state,
            "edge_block",
            from_junction=focused,
            to_junction=int(to_junction),
            mode=mode,
            turns=_clean_turns(turns),
        )
    elif block_type == "mode_block":
        if mode not in {"taxi", "bus", "subway"}:
            return _snapshot(state, selected, focused, "Choose taxi, bus, or subway first.", sound="map_select")
        state, message = add_block(state, "mode_block", junction_id=focused, mode=mode, turns=_clean_turns(turns))
    else:
        state, message = add_block(state, "junction_block", junction_id=focused, turns=_clean_turns(turns))

    _SESSIONS[state.game_id] = state
    return _snapshot(state, selected, focused, message, sound="blockade_set")


def api_place_tactic(
    game_id: str | None,
    tactic_type: str | None,
    junction_id: int | None,
    selected_junctions: list[int] | None = None,
    focused_junction: int | None = None,
) -> dict[str, Any]:
    state = _state_for(game_id)
    selected, focused = _selection_context(selected_junctions, focused_junction)
    target = _valid_junction(junction_id) or focused
    if target is None:
        return _snapshot(state, selected, focused, "Drop the tactic on a valid junction.", sound="map_select")
    junction = _junction_by_id(target)
    if junction is None:
        return _snapshot(state, selected, focused, "Drop the tactic on a valid junction.", sound="map_select")
    state, message = place_tactic(state, str(tactic_type or ""), target, int(junction["x"]), int(junction["y"]))
    _SESSIONS[state.game_id] = state
    return _snapshot(state, [*selected, target], target, message, sound="blockade_set")


def api_remove_tactic(
    game_id: str | None,
    tactic_id: str | None,
    selected_junctions: list[int] | None = None,
    focused_junction: int | None = None,
) -> dict[str, Any]:
    state = _state_for(game_id)
    selected, focused = _selection_context(selected_junctions, focused_junction)
    if not tactic_id:
        return _snapshot(state, selected, focused, "Choose a placed tactic first.", sound="map_select")
    state, message = remove_tactic(state, tactic_id)
    _SESSIONS[state.game_id] = state
    return _snapshot(state, selected, focused, message, sound="map_select")


def api_check_junctions(
    game_id: str | None,
    selected_junctions: list[int] | None = None,
    focused_junction: int | None = None,
) -> dict[str, Any]:
    state = _state_for(game_id)
    selected, focused = _selection_context(selected_junctions, focused_junction)
    targets = _ordered_check_targets(selected, focused)
    if not targets:
        return _snapshot(state, selected, focused, "Select at least one junction to search.", sound="map_select")

    remaining = checks_remaining_this_turn(state.turn_number, state.junction_checks)
    if remaining <= 0:
        return _snapshot(state, selected, focused, "No searches remain this turn.", sound="map_select")

    messages: list[str] = []
    for junction_id in targets[:remaining]:
        state, message = check_junction(state, junction_id)
        messages.append(f"J{junction_id}: {message}")
        if state.result:
            break

    _SESSIONS[state.game_id] = state
    return _snapshot(state, selected, focused, " ".join(messages), sound="blockade_set")


def api_ask_witness(
    game_id: str | None,
    witness_id: str | None,
    question: str = DEFAULT_QUESTION,
    selected_junctions: list[int] | None = None,
    focused_junction: int | None = None,
) -> dict[str, Any]:
    state = _state_for(game_id)
    selected, focused = _selection_context(selected_junctions, focused_junction)
    if not witness_id:
        return _snapshot(state, selected, focused, "Choose a witness card first.", sound="map_select")
    state, answer = question_witness(state, witness_id, question or DEFAULT_QUESTION)
    _SESSIONS[state.game_id] = state
    return _snapshot(state, selected, focused, answer, sound="witness_popup")


def api_advance_turn(
    game_id: str | None,
    selected_junctions: list[int] | None = None,
    focused_junction: int | None = None,
) -> dict[str, Any]:
    state = _state_for(game_id)
    selected, focused = _selection_context(selected_junctions, focused_junction)
    state, message = end_turn(state)
    _SESSIONS[state.game_id] = state
    return _snapshot(state, selected, focused, message, sound="turn_advance")


def api_settings() -> dict[str, Any]:
    settings = load_settings()
    return {
        "ok": True,
        "settings": _settings_payload(settings),
        "llama": _llama_status(settings),
        "difficulty_presets": {
            "easy": "Longer case, more checks, slower memory decay.",
            "normal": "Balanced turn limit, checks, and witness memory decay.",
            "hard": "Shorter case, fewer checks, faster witness memory decay.",
        },
    }


def api_update_settings(payload: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, str] = {}
    difficulty = str(payload.get("difficulty") or "").strip().lower()
    if difficulty in DIFFICULTY_PRESETS:
        updates.update(DIFFICULTY_PRESETS[difficulty])
        updates["PHANTOM_GRID_DIFFICULTY"] = difficulty

    field_map = {
        "llm_model": "PHANTOM_GRID_LLM_MODEL",
        "llamacpp_model_path": "PHANTOM_GRID_LLAMACPP_MODEL_PATH",
        "llamacpp_server_bin": "PHANTOM_GRID_LLAMACPP_SERVER_BIN",
        "llamacpp_base_url": "PHANTOM_GRID_LLAMACPP_BASE_URL",
        "max_turns": "PHANTOM_GRID_MAX_TURNS",
        "checks_per_turn": "PHANTOM_GRID_CHECKS_PER_TURN",
        "memory_corruption_per_turn": "PHANTOM_GRID_MEMORY_CORRUPTION_PER_TURN",
    }
    for field, env_key in field_map.items():
        if field in payload and payload[field] is not None:
            value = str(payload[field]).strip()
            if value:
                updates[env_key] = value

    if updates:
        _write_env_updates(updates)
        os.environ.update(updates)

    return api_settings()


def api_llama_action(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    if payload:
        api_update_settings(payload)
    settings = load_settings()
    normalized = action.strip().lower()
    if normalized == "status":
        return {"ok": True, "llama": _llama_status(settings), "settings": _settings_payload(settings)}
    if normalized == "stop":
        _stop_llama_process()
        return {"ok": True, "event": "llama-server stopped.", "llama": _llama_status(settings)}
    if normalized == "restart":
        _stop_llama_process()
        started = _start_llama_process(settings)
        return {"ok": started["ok"], "event": started["event"], "llama": _llama_status(load_settings())}
    if normalized == "start":
        started = _start_llama_process(settings)
        return {"ok": started["ok"], "event": started["event"], "llama": _llama_status(load_settings())}
    return {"ok": False, "event": f"Unknown llama action: {action}", "llama": _llama_status(settings)}


def game_snapshot(game_id: str | None = None) -> dict[str, Any]:
    state = _state_for(game_id, required=False)
    return _snapshot(state, [], None, "Ready.")


def nearest_junction_for_point(x: int, y: int, max_distance: int = MAP_CLICK_RADIUS) -> int | None:
    best_id: int | None = None
    best_distance = float(max_distance)
    for junction in _junction_records():
        distance = math.dist((x, y), (int(junction["x"]), int(junction["y"])))
        if distance <= best_distance:
            best_id = int(junction["id"])
            best_distance = distance
    return best_id


def junctions_for_drag_path(points: list[dict[str, int]], max_distance: int = MAP_CLICK_RADIUS) -> list[int]:
    selected: list[int] = []
    for point in points:
        x = _optional_int(point.get("x"))
        y = _optional_int(point.get("y"))
        if x is None or y is None:
            continue
        for junction in _junction_records():
            junction_id = int(junction["id"])
            if junction_id in selected:
                continue
            if math.dist((x, y), (int(junction["x"]), int(junction["y"]))) <= max_distance:
                selected.append(junction_id)
    return selected


def toggle_junction_selection(current: list[int], junction_id: int) -> list[int]:
    clean = _valid_junctions(current)
    valid = _valid_junction(junction_id)
    if valid is None:
        return clean
    if valid in clean:
        return [item for item in clean if item != valid]
    return [*clean, valid]


def _snapshot(
    state: GameState | None,
    selected_junctions: list[int] | None = None,
    focused_junction: int | None = None,
    event: str = "",
    sound: str | None = None,
) -> dict[str, Any]:
    selected, focused = _selection_context(selected_junctions, focused_junction)
    return {
        "ok": True,
        "event": event,
        "sound": sound,
        "game": _visible_game_state(state),
        "map": _map_payload(),
        "selection": {
            "junctions": selected,
            "focused": focused,
            "legal_moves": _legal_moves_payload(focused, state),
        },
        "lookout": _lookout_payload(state),
        "witness_locations": _witness_locations(state),
        "witness_cards": _witness_cards(state),
        "previous_statements": _previous_statements(state),
        "active_blocks": _active_blocks_payload(state),
        "placed_tactics": _placed_tactics_payload(state),
        "tactic_counts": _tactic_counts_payload(state),
        "events": _public_events(state),
        "asset_prompts": _asset_prompts(),
    }


def _visible_game_state(state: GameState | None) -> dict[str, Any] | None:
    if state is None:
        return None
    return {
        "game_id": state.game_id,
        "turn": state.turn_number,
        "max_turns": state.max_turns,
        "phase": state.phase,
        "result": state.result,
        "checks_remaining": checks_remaining_this_turn(state.turn_number, state.junction_checks),
        "notices": len(state.notices),
        "witness_batches": len(state.witness_batches),
        "initial_description": state.initial_description,
    }


def _map_payload() -> dict[str, Any]:
    metadata = load_map_metadata()
    return {
        "layers": list(metadata.get("images", {}).keys()),
        "default_layer": "normal",
        "junctions": _junction_records(),
    }


def _legal_moves_payload(focused_junction: int | None, state: GameState | None) -> list[dict[str, Any]]:
    if focused_junction is None:
        return []
    blocks = [asdict(block) for block in state.active_blocks] if state else None
    return [
        {
            "destination": move.destination,
            "mode": move.mode,
            "blocked": move.blocked,
            "label": f"J{focused_junction} to J{move.destination} by {move.mode}",
        }
        for move in legal_moves_from(focused_junction, blocks)
    ]


def _lookout_payload(state: GameState | None) -> dict[str, Any]:
    if state is None or not state.witness_batches:
        return {"raised": False, "witness_count": 0, "review_allowed": False, "notice": None}
    batch = state.witness_batches[-1]
    notice = next((item for item in state.notices if item.notice_id == batch.notice_id), None)
    return {
        "raised": True,
        "witness_count": batch.total_witnesses,
        "review_allowed": batch.individual_review_allowed,
        "notice": notice.text if notice else "",
        "parsed_location": notice.parsed_location if notice else "",
    }


def _witness_locations(state: GameState | None) -> list[dict[str, Any]]:
    if state is None or not state.witness_batches:
        return []
    batch = state.witness_batches[-1]
    distribution: dict[int, dict[str, Any]] = {}
    for witness in batch.witnesses:
        location = distribution.setdefault(
            witness.junction_id,
            {
                "junction_id": witness.junction_id,
                "count": 0,
                "inspectable": batch.individual_review_allowed,
                "sample_witness_id": witness.witness_id,
                "sample_style": witness.personality.get("style", "witness"),
                "sample_summary": witness.current_summary,
                "sample_relevance": witness.relevance_score,
                "viewed": False,
            },
        )
        location["count"] += 1
        if state and witness.witness_id in state.viewed_witness_ids:
            location["viewed"] = True
        if witness.relevance_score > location["sample_relevance"]:
            already_viewed = bool(location.get("viewed"))
            location["sample_witness_id"] = witness.witness_id
            location["sample_style"] = witness.personality.get("style", "witness")
            location["sample_summary"] = witness.current_summary
            location["sample_relevance"] = witness.relevance_score
            location["viewed"] = already_viewed or (state is not None and witness.witness_id in state.viewed_witness_ids)
    return [
        distribution[junction_id]
        for junction_id in sorted(distribution)
    ]


def _witness_cards(state: GameState | None) -> list[dict[str, Any]]:
    if state is None:
        return []
    cards: list[dict[str, Any]] = []
    for batch in state.witness_batches:
        if not batch.individual_review_allowed:
            continue
        for witness in batch.witnesses:
            cards.append(
                {
                    "id": witness.witness_id,
                    "junction_id": witness.junction_id,
                    "reliability": witness.reliability,
                    "memory": witness.memory_strength,
                    "relevance": witness.relevance_score,
                    "style": witness.personality.get("style", "witness"),
                    "summary": witness.current_summary,
                    "questions": [asdict(question) for question in witness.question_history[-2:]],
                    "viewed": witness.witness_id in state.viewed_witness_ids,
                }
            )
    return cards[-18:]


def _previous_statements(state: GameState | None) -> list[dict[str, Any]]:
    if state is None:
        return []
    statements: list[dict[str, Any]] = []
    for batch in state.witness_batches:
        for witness in batch.witnesses:
            if witness.witness_id not in state.viewed_witness_ids or not witness.question_history:
                continue
            latest = witness.question_history[-1]
            statements.append(
                {
                    "id": witness.witness_id,
                    "turn": latest.turn_number,
                    "junction_id": witness.junction_id,
                    "time_label": _time_label(latest.turn_number),
                    "summary": witness.current_summary,
                    "question": latest.question,
                    "answer": latest.answer,
                    "viewed": True,
                }
            )
    return statements[-8:]


def _active_blocks_payload(state: GameState | None) -> list[dict[str, Any]]:
    if state is None:
        return []
    blocks: list[dict[str, Any]] = []
    for block in state.active_blocks:
        if block.block_type == "edge_block":
            label = f"J{block.from_junction} to J{block.to_junction}"
        elif block.block_type == "mode_block":
            label = f"{block.mode} near J{block.junction_id or 'all'}"
        else:
            label = f"J{block.junction_id}"
        blocks.append({**asdict(block), "label": label})
    return blocks


def _placed_tactics_payload(state: GameState | None) -> list[dict[str, Any]]:
    if state is None:
        return []
    return [asdict(tactic) for tactic in state.placed_tactics]


def _tactic_counts_payload(state: GameState | None) -> dict[str, Any]:
    placed_counts = {key: 0 for key in TACTIC_LIMITS}
    if state is not None:
        for tactic in state.placed_tactics:
            if tactic.tactic_type in placed_counts:
                placed_counts[tactic.tactic_type] += 1
    remaining = {
        key: max(limit - placed_counts.get(key, 0), 0)
        for key, limit in TACTIC_LIMITS.items()
    }
    return {
        "limits": TACTIC_LIMITS,
        "placed": placed_counts,
        "remaining": remaining,
        "total_limit": sum(TACTIC_LIMITS.values()),
        "total_remaining": sum(remaining.values()),
    }


def _public_events(state: GameState | None) -> list[dict[str, Any]]:
    if state is None:
        return []
    return [
        entry
        for entry in state.game_log[-12:]
        if entry.get("kind") != "culprit_move_private"
    ][-6:]


def _asset_prompts() -> dict[str, str]:
    return {
        "case_table_background": "top-down view of a moody London detective desk, paper map, pins, string, chalk dust, warm lamp light, stylized game UI background, no text",
        "suspect_placeholder": "anonymous noir suspect silhouette in a grey raincoat holding a red folder, graphic novel style, transparent background, no text",
        "witness_card_set": "four small portrait cards of London street witnesses, varied ages and moods, 1930s detective board style, consistent illustration style, no text",
        "lookout_board_texture": "green-black chalkboard with faint chalk smudges and taped paper edges, game UI texture, no readable text",
        "map_select": "short tactile wooden token tap on a board, warm room tone, 0.3 seconds",
        "blockade_set": "metal stamp clack with soft paper thud, detective office, 0.5 seconds",
        "lookout_raise": "chalk scrape and corkboard paper rustle, subtle, 0.8 seconds",
        "witness_popup": "quick paper card flick with faint bell, playful noir, 0.4 seconds",
        "turn_advance": "old clock tick plus distant city ambience swell, 1 second",
    }


def _settings_payload(settings) -> dict[str, Any]:
    return {
        "llm_model": settings.llm_model,
        "llamacpp_model_path": str(settings.llamacpp_model_path or ""),
        "llamacpp_model_exists": bool(settings.llamacpp_model_path and settings.llamacpp_model_path.exists()),
        "llamacpp_server_bin": str(settings.llamacpp_server_bin or ""),
        "llamacpp_server_bin_exists": bool(settings.llamacpp_server_bin and settings.llamacpp_server_bin.exists()),
        "llamacpp_base_url": settings.llamacpp_base_url,
        "difficulty": os.getenv("PHANTOM_GRID_DIFFICULTY", _difficulty_from_settings(settings)),
        "max_turns": settings.max_turns,
        "checks_per_turn": settings.checks_per_turn,
        "memory_corruption_per_turn": settings.memory_corruption_per_turn,
    }


def _difficulty_from_settings(settings) -> str:
    if settings.max_turns >= 16 or settings.checks_per_turn >= 3:
        return "easy"
    if settings.max_turns <= 10 or settings.checks_per_turn <= 1:
        return "hard"
    return "normal"


def _llama_status(settings) -> dict[str, Any]:
    global _LLAMA_PROCESS
    if _LLAMA_PROCESS is not None and _LLAMA_PROCESS.poll() is not None:
        _LLAMA_PROCESS = None
    reachable = False
    detail = "Not reachable."
    try:
        url = f"{settings.llamacpp_base_url.rstrip('/')}/models"
        with urllib.request.urlopen(url, timeout=1.5) as response:
            reachable = 200 <= response.status < 500
            detail = "Reachable." if reachable else f"HTTP {response.status}."
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        detail = f"Not reachable: {exc.__class__.__name__}."
    return {
        "managed_process": _LLAMA_PROCESS is not None,
        "pid": _LLAMA_PROCESS.pid if _LLAMA_PROCESS is not None else None,
        "reachable": reachable,
        "detail": detail,
    }


def _start_llama_process(settings) -> dict[str, Any]:
    global _LLAMA_PROCESS
    if _LLAMA_PROCESS is not None and _LLAMA_PROCESS.poll() is None:
        return {"ok": True, "event": f"llama-server is already managed as PID {_LLAMA_PROCESS.pid}."}
    if not settings.llamacpp_server_bin or not settings.llamacpp_server_bin.exists():
        return {"ok": False, "event": "Set a valid llama-server binary path before starting."}
    if not settings.llamacpp_model_path or not settings.llamacpp_model_path.exists():
        return {"ok": False, "event": "Set a valid GGUF model path before starting."}

    port = _port_from_base_url(settings.llamacpp_base_url)
    args = [
        str(settings.llamacpp_server_bin),
        "-m",
        str(settings.llamacpp_model_path),
        "--port",
        str(port),
    ]
    try:
        _LLAMA_PROCESS = subprocess.Popen(
            args,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except OSError as exc:
        return {"ok": False, "event": f"Could not start llama-server: {exc}"}
    return {"ok": True, "event": f"llama-server started as PID {_LLAMA_PROCESS.pid}."}


def _stop_llama_process() -> None:
    global _LLAMA_PROCESS
    if _LLAMA_PROCESS is None:
        return
    if _LLAMA_PROCESS.poll() is None:
        _LLAMA_PROCESS.terminate()
        try:
            _LLAMA_PROCESS.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _LLAMA_PROCESS.kill()
    _LLAMA_PROCESS = None


def _port_from_base_url(base_url: str) -> int:
    try:
        from urllib.parse import urlparse

        parsed = urlparse(base_url)
        return parsed.port or 8080
    except ValueError:
        return 8080


def _write_env_updates(updates: dict[str, str]) -> None:
    env_path = PROJECT_ROOT / ".env"
    existing: dict[str, str] = {}
    order: list[str] = []
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip() or raw_line.strip().startswith("#") or "=" not in raw_line:
                continue
            key, value = raw_line.split("=", 1)
            key = key.strip()
            existing[key] = value.strip().strip('"').strip("'")
            order.append(key)
    existing.update(updates)
    for key in updates:
        if key not in order:
            order.append(key)
    lines = [f"{key}={existing[key]}" for key in order if key in existing]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _junction_by_id(junction_id: int) -> dict[str, Any] | None:
    return next((junction for junction in _junction_records() if int(junction["id"]) == junction_id), None)


def _time_label(turn_number: int) -> str:
    labels = ["morning", "midday", "afternoon", "evening", "night"]
    return labels[(turn_number - 1) % len(labels)]


def _state_for(game_id: str | None, required: bool = True) -> GameState | None:
    if not game_id:
        if required:
            raise HTTPException(status_code=400, detail="Start a case first.")
        return None
    state = _SESSIONS.get(game_id)
    if state is None and required:
        raise HTTPException(status_code=404, detail="Case not found. Start a new case.")
    return state


def _selection_context(
    selected_junctions: list[int] | None,
    focused_junction: int | None,
) -> tuple[list[int], int | None]:
    selected = _valid_junctions(selected_junctions or [])
    focused = _valid_junction(focused_junction)
    if focused is None and selected:
        focused = selected[-1]
    if focused is not None and focused not in selected:
        selected = [*selected, focused]
    return selected, focused


def _ordered_check_targets(selected_junctions: list[int], focused_junction: int | None) -> list[int]:
    targets: list[int] = []
    if focused_junction is not None:
        targets.append(focused_junction)
    for junction_id in selected_junctions:
        if junction_id not in targets:
            targets.append(junction_id)
    return targets


def _valid_junctions(junctions: list[int]) -> list[int]:
    valid_ids = set(all_junction_ids())
    clean: list[int] = []
    for raw in junctions:
        junction_id = _optional_int(raw)
        if junction_id in valid_ids and junction_id not in clean:
            clean.append(junction_id)
    return clean


def _valid_junction(junction_id: int | None) -> int | None:
    parsed = _optional_int(junction_id)
    if parsed in set(all_junction_ids()):
        return parsed
    return None


def _selection_event(selected_junctions: list[int], focused_junction: int | None) -> str:
    if focused_junction is None:
        return "No junction selected."
    count = len(selected_junctions)
    return f"J{focused_junction} focused. {count} selected."


def _notice_with_selected_junction(notice_text: str, selected_junction: int | None) -> str:
    if selected_junction is None:
        return notice_text.replace("selected junction", "the search area")
    return notice_text.replace("selected junction", f"Junction {selected_junction}")


def _clean_turns(turns: int | str | None) -> int:
    parsed = _optional_int(turns)
    if parsed is None:
        return 1
    return min(max(parsed, 1), 3)


def _junction_records() -> list[dict[str, Any]]:
    settings = load_settings()
    data = read_json(settings.junction_registry_path)
    return data.get("junctions", [])


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _case_state_text(state: GameState) -> str:
    remaining = max(state.max_turns - state.turn_number + 1, 0)
    checks_used = sum(1 for check in state.junction_checks if check.turn_number == state.turn_number)
    return "\n".join(
        [
            f"Game: {state.game_id}",
            f"Turn: {state.turn_number} / {state.max_turns}",
            f"Turns remaining: {remaining}",
            f"Phase: {state.phase}",
            f"Result: {state.result or 'in progress'}",
            f"Initial description: {state.initial_description}",
            f"Checks used this turn: {checks_used}",
            f"Notices issued: {len(state.notices)}",
            f"Witness batches: {len(state.witness_batches)}",
        ]
    )


def _witness_batches_text(state: GameState) -> str:
    if not state.witness_batches:
        return "No witness batches yet."
    lines: list[str] = []
    for batch in state.witness_batches[-4:]:
        notice = next((notice for notice in state.notices if notice.notice_id == batch.notice_id), None)
        lines.append(f"{batch.batch_id}: {batch.total_witnesses} witnesses")
        if notice:
            lines.append(f"Notice: {notice.text}")
            lines.append(f"Parsed location: {notice.parsed_location}")
        lines.append("Individual review: " + ("available" if batch.individual_review_allowed else "unavailable"))
    return "\n".join(lines).strip()


def _active_blocks_text(state: GameState) -> str:
    if not state.active_blocks:
        return "No active blocks."
    return "\n".join(
        f"{block.block_id}: {block.block_type}, mode={block.mode or 'any'}, junction={block.junction_id}, edge={block.from_junction}->{block.to_junction}, turns={block.turns_remaining}"
        for block in state.active_blocks
    )


def _game_log_text(state: GameState) -> str:
    return "\n".join(f"T{entry['turn_number']} {entry['kind']}: {entry['message']}" for entry in state.game_log[-12:])


if __name__ == "__main__":
    build_app().launch(server_name="127.0.0.1", server_port=7860, allowed_paths=[str(PROJECT_ROOT)])
