from __future__ import annotations

import asyncio
import base64
import json
import math
import os
import random
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any

import gradio as gr
from fastapi import HTTPException, WebSocket, WebSocketDisconnect
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
    persist,
    question_witness,
    remove_tactic,
    finalize_game,
    update_notes,
)
from game.save_load import load_state
from game.state import GameState, WitnessQuestion
from game.story_engine import compact_story_memory, ensure_case_introduction, story_reveal
from game.context_budget import ContextBudget, normalize_context_length
from game.witness_engine import deterministic_witness_answer, witness_by_id
from grid_map.atlas import public_atlas_payload
from grid_map.graph_loader import all_junction_ids, legal_moves_from
from grid_map.map_loader import image_for_layer, load_map_metadata
from grid_map.storage import read_json
from llm.omni_client import OmniClient, scan_minicpm_models
from llm.audio import wav_to_float32_base64
from llm.devices import (
    context_length_presets,
    detect_devices,
    gpu_layer_presets,
    quantization_catalog,
    resolve_device_env,
)

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
_SETUP_PROCESS: subprocess.Popen | None = None
RUNTIME_ROOT = PROJECT_ROOT / "runtime"

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

    @app.get("/assets/voices/{voice_id}")
    async def voice_asset(voice_id: str) -> FileResponse:
        path = _voice_path(voice_id)
        if path is None:
            raise HTTPException(status_code=404, detail="Unknown witness voice.")
        return FileResponse(path, media_type="audio/wav")

    @app.get("/api/snapshot")
    async def snapshot_route(game_id: str | None = None) -> dict[str, Any]:
        return game_snapshot(game_id)

    @app.post("/api/new_case")
    async def new_case_route(payload: dict[str, Any]) -> dict[str, Any]:
        return new_case(payload.get("initial_description") or DEFAULT_DESCRIPTION, require_omni=True)

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
            layer=payload.get("layer"),
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
            use_model=True,
        )

    @app.post("/api/advance_turn")
    async def advance_turn_route(payload: dict[str, Any]) -> dict[str, Any]:
        return api_advance_turn(
            payload.get("game_id"),
            payload.get("selected_junctions") or [],
            payload.get("focused_junction"),
            use_model=True,
        )

    @app.get("/api/omni/status")
    async def omni_status_route() -> dict[str, Any]:
        return api_omni_status()

    @app.get("/api/omni/models")
    async def omni_models_route() -> dict[str, Any]:
        return api_omni_models()

    @app.post("/api/game/{game_id}/notes")
    async def notes_route(game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = _state_for(game_id)
        update_notes(state, str(payload.get("notes") or ""))
        return {"ok": True, "notes": state.user_notes}

    @app.post("/api/game/{game_id}/stop")
    async def stop_game_route(game_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        state = _state_for(game_id)
        reveal = finalize_game(state, str((payload or {}).get("reason") or "stopped"))
        snapshot = _snapshot(state, [], None, "Case finalized.")
        snapshot["story_available"] = False
        return {"ok": True, "story": reveal, "snapshot": snapshot}

    @app.get("/api/game/{game_id}/story")
    async def story_route(game_id: str) -> dict[str, Any]:
        state = _state_for(game_id)
        if not state.result and not state.finalized_reason:
            raise HTTPException(status_code=403, detail="The private story is revealed only after the case ends.")
        return {"ok": True, "story": story_reveal(state)}

    @app.get("/api/witness/{game_id}/{witness_id}")
    async def witness_route(game_id: str, witness_id: str) -> dict[str, Any]:
        return api_witness_detail(game_id, witness_id)

    @app.post("/api/witness/{game_id}/{witness_id}/message")
    async def witness_message_route(game_id: str, witness_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return api_witness_message(game_id, witness_id, str(payload.get("message") or ""))

    @app.websocket("/ws/witness/{game_id}/{witness_id}")
    async def witness_socket(websocket: WebSocket, game_id: str, witness_id: str) -> None:
        await proxy_witness_socket(websocket, game_id, witness_id)

    @app.get("/api/settings")
    async def settings_route() -> dict[str, Any]:
        return api_settings()

    @app.post("/api/settings")
    async def update_settings_route(payload: dict[str, Any]) -> dict[str, Any]:
        return api_update_settings(payload)

    @app.post("/api/llama/{action}")
    async def llama_action_route(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return api_llama_action(action, payload or {})

    @app.get("/api/setup/status")
    async def setup_status_route() -> dict[str, Any]:
        return api_setup_status()

    @app.post("/api/setup/start")
    async def setup_start_route(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return api_setup_start(payload or {})

    @app.get("/api/runtime/options")
    async def runtime_options_route() -> dict[str, Any]:
        return api_runtime_options()

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


def new_case(initial_description: str = DEFAULT_DESCRIPTION, require_omni: bool = False) -> dict[str, Any]:
    if require_omni:
        health = OmniClient.from_settings().health()
        if not health.get("ready"):
            raise HTTPException(status_code=503, detail="MiniCPM-o must be healthy before a new case can start.")
    state = new_game(initial_description or DEFAULT_DESCRIPTION, use_model=require_omni)
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
    state, batch = issue_notice(state, text, anchor_junction=focused)
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
    layer: str | None = None,
) -> dict[str, Any]:
    state = _state_for(game_id)
    selected, focused = _selection_context(selected_junctions, focused_junction)
    target = _valid_junction(junction_id) or focused
    if target is None:
        return _snapshot(state, selected, focused, "Drop the tactic on a valid junction.", sound="map_select")
    junction = _junction_by_id(target)
    if junction is None:
        return _snapshot(state, selected, focused, "Drop the tactic on a valid junction.", sound="map_select")
    state, message = place_tactic(state, str(tactic_type or ""), target, int(junction["x"]), int(junction["y"]), layer=layer)
    _SESSIONS[state.game_id] = state
    snapshot = _snapshot(state, [*selected, target], target, message, sound="blockade_set")
    if tactic_type == "lookout_board" and "No lookout" not in message:
        snapshot["notice_prompt"] = {
            "open": True,
            "junction_id": target,
            "prefill": state.last_notice_text or state.initial_description,
        }
    return snapshot


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
    use_model: bool = False,
) -> dict[str, Any]:
    state = _state_for(game_id)
    selected, focused = _selection_context(selected_junctions, focused_junction)
    if not witness_id:
        return _snapshot(state, selected, focused, "Choose a witness card first.", sound="map_select")
    if use_model:
        _require_omni_ready()
    state, answer = question_witness(state, witness_id, question or DEFAULT_QUESTION, use_model=use_model)
    _SESSIONS[state.game_id] = state
    return _snapshot(state, selected, focused, answer, sound="witness_popup")


def api_advance_turn(
    game_id: str | None,
    selected_junctions: list[int] | None = None,
    focused_junction: int | None = None,
    use_model: bool = False,
) -> dict[str, Any]:
    state = _state_for(game_id)
    selected, focused = _selection_context(selected_junctions, focused_junction)
    if use_model:
        _require_omni_ready()
    state.effective_context_length = load_settings().llamacpp_context_length
    compact_story_memory(state)
    previous_batch_count = len(state.witness_batches)
    state, message = end_turn(state, use_model=use_model)
    _SESSIONS[state.game_id] = state
    sound = "witness_popup" if len(state.witness_batches) > previous_batch_count else "turn_advance"
    return _snapshot(state, selected, focused, message, sound=sound)


def api_witness_detail(game_id: str, witness_id: str) -> dict[str, Any]:
    state = _state_for(game_id)
    witness = witness_by_id(state, witness_id)
    if witness is None:
        raise HTTPException(status_code=404, detail="Witness not found or not yet surfaced.")
    if witness_id not in state.viewed_witness_ids:
        state.viewed_witness_ids.append(witness_id)
        persist(state)
    return {
        "ok": True,
        "witness": {
            "id": witness.witness_id,
            "name": witness.name,
            "occupation": witness.occupation,
            "junction_id": witness.junction_id,
            "personality": witness.personality,
            "reliability": witness.reliability,
            "memory": witness.memory_strength,
            "summary": witness.current_summary,
            "voice_id": witness.voice_id,
            "voice_url": f"/assets/voices/{witness.voice_id}",
            "transcript": [asdict(item) for item in witness.question_history],
        },
    }


_CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


def _witness_chat_with_english_retry(settings, system_prompt, user_prompt, voice_path):
    # MiniCPM-o-4.5 Q4_K_M still slips into Chinese filler maybe 1 reply in 4
    # even with a plain English prompt. If we detect CJK in the response, retry
    # once at a lower temperature with a sharper directive — that produces a
    # clean English answer in nearly every case.
    client = OmniClient(settings)
    ref_path = str(voice_path) if voice_path else None
    response = client.chat(
        system_prompt, user_prompt, task="interview", temperature=0.55,
        tts=settings.witness_chat_tts, ref_audio_path=ref_path,
    )
    if not _CJK_RE.search(response.text or ""):
        return response
    retry_system = (
        system_prompt + " Your previous attempt contained Chinese characters; "
        "this attempt MUST be English only — no Chinese characters at all."
    )
    return client.chat(
        retry_system, user_prompt, task="interview", temperature=0.2,
        tts=settings.witness_chat_tts, ref_audio_path=ref_path,
    )


def api_witness_message(game_id: str, witness_id: str, message: str) -> dict[str, Any]:
    clean = " ".join(message.split())[:2000]
    if not clean:
        raise HTTPException(status_code=400, detail="Enter a question for the witness.")
    _require_omni_ready()
    state = _state_for(game_id)
    witness = witness_by_id(state, witness_id)
    if witness is None:
        raise HTTPException(status_code=404, detail="Witness not found or not yet surfaced.")
    voice_path = _voice_path(witness.voice_id)
    settings = load_settings()
    budget = ContextBudget.for_context(settings.llamacpp_context_length)
    # MiniCPM-o-4.5 Q4_K_M reliably degrades to Chinese filler when given a JSON
    # blob as the user message — its Chinese assistant prior overwhelms a
    # prompt it can't parse. Plain English with the question on the last line
    # produces consistent on-topic English replies.
    history = witness.question_history[-budget.recent_interview_turns :]
    system_prompt = (
        "You are roleplaying a witness in an English-language detective game. "
        "Speak only English. Reply in one or two short sentences. Use only the "
        "facts the user gives you. Let the supplied personality control tone, "
        "confidence, and brevity. Never invent details. If you don't know, say "
        "you don't know."
    )
    history_block = (
        "\n".join(f"  Detective: {item.question}\n  You: {item.answer}" for item in history)
        if history else "  (no prior questions)"
    )
    stable_block = ", ".join(witness.stable_facts) if witness.stable_facts else "(none recorded)"
    personality_block = ", ".join(f"{k}: {v}" for k, v in witness.personality.items()) or "ordinary"
    user_prompt = (
        f"You are {witness.name}, a {witness.occupation} ({personality_block}).\n"
        f"What you saw / know: {witness.current_summary}\n"
        f"Stable facts: {stable_block}\n"
        f"Conversation so far:\n{history_block}\n"
        f"The detective now asks: {clean!r}\n"
        f"Reply in character, in English, in one or two short sentences."
    )
    response = _witness_chat_with_english_retry(
        settings, system_prompt, user_prompt, voice_path,
    )
    answer = response.text.strip() or deterministic_witness_answer(witness, clean)
    witness.question_history.append(WitnessQuestion(question=clean, answer=answer, turn_number=state.turn_number))
    if witness_id not in state.viewed_witness_ids:
        state.viewed_witness_ids.append(witness_id)
    persist(state)
    return {
        "ok": True,
        "answer": answer,
        "audio_data": response.audio_data,
        "audio_sample_rate": response.audio_sample_rate or 24000,
        "snapshot": _snapshot(state, [witness.junction_id], witness.junction_id),
    }


async def proxy_witness_socket(websocket: WebSocket, game_id: str, witness_id: str) -> None:
    state = _state_for(game_id)
    witness = witness_by_id(state, witness_id)
    if witness is None:
        await websocket.close(code=1008, reason="Witness not available")
        return
    if not OmniClient.from_settings().omni_health().get("ready"):
        await websocket.close(code=1013, reason="MiniCPM-o service unavailable")
        return
    await websocket.accept()
    settings = load_settings()
    gateway = settings.omni_gateway_url.rstrip("/")
    if gateway.startswith("https://"):
        gateway = "wss://" + gateway[8:]
    elif gateway.startswith("http://"):
        gateway = "ws://" + gateway[7:]
    session_id = f"{game_id}_{witness_id}".replace("/", "_")[-180:]
    target = f"{gateway}/ws/half_duplex/{session_id}"
    voice_path = _voice_path(witness.voice_id)
    voice_b64, voice_duration = wav_to_float32_base64(voice_path) if voice_path else ("", 0.0)
    assistant_chunks: list[str] = []
    try:
        import websockets

        async with websockets.connect(target, max_size=32 * 1024 * 1024) as upstream:
            async def client_to_upstream() -> None:
                async for raw in websocket.iter_text():
                    data = json.loads(raw)
                    if data.get("type") == "prepare":
                        budget = ContextBudget.for_context(settings.llamacpp_context_length)
                        data["system_content"] = [
                            {"type": "text", "text": f"Clone this voice. You are {witness.name}, a {witness.occupation}. Speak only from this knowledge: {witness.current_summary}"},
                            {
                                "type": "audio",
                                "data": voice_b64,
                                "name": f"{witness.voice_id}.wav",
                                "duration": voice_duration,
                            },
                            {"type": "text", "text": "Stay in character. Reply in English only — do not translate or speak Chinese. Be concise, and never invent hidden facts."},
                        ]
                        data["lang"] = "en"
                        data["config"] = {
                            "vad": {
                                "threshold": 0.5,
                                "min_speech_duration_ms": 128,
                                "min_silence_duration_ms": 600,
                                "speech_pad_ms": 30,
                            },
                            "generation": {
                                "max_new_tokens": min(96, budget.output_tokens),
                                "length_penalty": 1.1,
                                "temperature": 0.7,
                            },
                            "tts": {"enabled": True},
                            "session": {"timeout_s": 300},
                        }
                    await upstream.send(json.dumps(data))

            async def upstream_to_client() -> None:
                async for raw in upstream:
                    data = json.loads(raw)
                    if data.get("text_delta"):
                        assistant_chunks.append(str(data["text_delta"]))
                    if data.get("type") == "turn_done" and assistant_chunks:
                        answer = "".join(assistant_chunks).strip()
                        assistant_chunks.clear()
                        witness.question_history.append(WitnessQuestion(
                            question="[Spoken question]", answer=answer, turn_number=state.turn_number
                        ))
                        if witness_id not in state.viewed_witness_ids:
                            state.viewed_witness_ids.append(witness_id)
                        persist(state)
                    await websocket.send_text(raw)

            tasks = [asyncio.create_task(client_to_upstream()), asyncio.create_task(upstream_to_client())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
    except (WebSocketDisconnect, OSError, ValueError, json.JSONDecodeError) as exc:
        try:
            await websocket.send_json({"type": "error", "error": str(exc)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


def api_settings() -> dict[str, Any]:
    settings = load_settings()
    llama_status, omni_status = _service_statuses(settings)
    return {
        "ok": True,
        "settings": _settings_payload(settings),
        "llama": llama_status,
        "omni": omni_status,
        "model_scan": scan_minicpm_models(settings.minicpm_model_dir),
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
        "llm_provider": "PHANTOM_GRID_LLM_PROVIDER",
        "llm_model": "PHANTOM_GRID_LLM_MODEL",
        "llamacpp_model_path": "PHANTOM_GRID_LLAMACPP_MODEL_PATH",
        "llamacpp_server_bin": "PHANTOM_GRID_LLAMACPP_SERVER_BIN",
        "llamacpp_base_url": "PHANTOM_GRID_LLAMACPP_BASE_URL",
        "max_turns": "PHANTOM_GRID_MAX_TURNS",
        "checks_per_turn": "PHANTOM_GRID_CHECKS_PER_TURN",
        "memory_corruption_per_turn": "PHANTOM_GRID_MEMORY_CORRUPTION_PER_TURN",
        "omni_gateway_url": "PHANTOM_GRID_OMNI_GATEWAY_URL",
        "omni_launcher_path": "PHANTOM_GRID_OMNI_LAUNCHER_PATH",
        "comni_checkout_path": "PHANTOM_GRID_COMNI_CHECKOUT_PATH",
        "llamacpp_omni_root": "PHANTOM_GRID_LLAMACPP_OMNI_ROOT",
        "minicpm_model_dir": "PHANTOM_GRID_MINICPM_MODEL_DIR",
        "minicpm_quantization": "PHANTOM_GRID_MINICPM_QUANTIZATION",
        "llamacpp_gpu_layers": "PHANTOM_GRID_LLAMACPP_GPU_LAYERS",
        "minicpm_gpu_device": "PHANTOM_GRID_GPU_DEVICE",
        "witness_voice_dir": "PHANTOM_GRID_WITNESS_VOICE_DIR",
    }
    for field, env_key in field_map.items():
        if field in payload and payload[field] is not None:
            value = str(payload[field]).strip()
            if value:
                updates[env_key] = value

    if "llamacpp_context_length" in payload:
        try:
            updates["PHANTOM_GRID_LLAMACPP_CONTEXT_LENGTH"] = str(normalize_context_length(payload["llamacpp_context_length"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if "llamacpp_gpu_layers" in payload:
        gpu_layers = str(payload["llamacpp_gpu_layers"]).strip().lower()
        if gpu_layers != "auto":
            try:
                if int(gpu_layers) < 0:
                    raise ValueError
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="GPU layers must be 'auto' or a non-negative integer.") from exc
        updates["PHANTOM_GRID_LLAMACPP_GPU_LAYERS"] = gpu_layers

    provider = updates.get("PHANTOM_GRID_LLM_PROVIDER", load_settings().llm_provider)
    if provider not in {"minicpm_omni", "llama_cpp_server", "external_llama_cpp_server"}:
        raise HTTPException(status_code=400, detail="Choose a supported AI backend.")
    if provider == "llama_cpp_server":
        model_path = Path(updates.get("PHANTOM_GRID_LLAMACPP_MODEL_PATH") or str(load_settings().llamacpp_model_path or ""))
        if not model_path.is_file() or model_path.suffix.lower() != ".gguf":
            raise HTTPException(status_code=400, detail="Choose an existing .gguf model file for the standalone llama.cpp backend.")
        server_bin = Path(updates.get("PHANTOM_GRID_LLAMACPP_SERVER_BIN") or str(load_settings().llamacpp_server_bin or ""))
        if not server_bin.is_file():
            raise HTTPException(status_code=400, detail="Choose an existing llama-server executable.")
        updates["PHANTOM_GRID_LLM_MODEL"] = model_path.name
    elif provider == "external_llama_cpp_server":
        base_url = updates.get("PHANTOM_GRID_LLAMACPP_BASE_URL", load_settings().llamacpp_base_url).rstrip("/")
        model = updates.get("PHANTOM_GRID_LLM_MODEL", load_settings().llm_model).strip()
        if not base_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="External server URL must start with http:// or https://.")
        if not model:
            raise HTTPException(status_code=400, detail="Enter the model ID exposed by the external llama.cpp server.")
        updates["PHANTOM_GRID_LLAMACPP_BASE_URL"] = base_url

    model_dir = Path(updates.get("PHANTOM_GRID_MINICPM_MODEL_DIR") or str(load_settings().minicpm_model_dir or ""))
    selected = updates.get("PHANTOM_GRID_MINICPM_QUANTIZATION")
    if selected:
        catalog_names = {item["id"] for item in quantization_catalog()}
        on_disk_names = {item["filename"] for item in scan_minicpm_models(model_dir).get("models", [])}
        # Allow catalog entries even when the file isn't on disk yet — this is the
        # first-run case where the user is choosing what the provisioner should
        # download. Otherwise require the file to already be present.
        if selected not in catalog_names and selected not in on_disk_names:
            raise HTTPException(status_code=400, detail="Selected quantization is not a compatible MiniCPM-o LLM GGUF file.")

    if "minicpm_gpu_device" in payload:
        device_id = str(payload["minicpm_gpu_device"]).strip()
        if device_id:
            valid_device_ids = {item["id"] for item in detect_devices()}
            # Accept stored ids that simply aren't present anymore (e.g. external
            # GPU unplugged) — we just warn via the picker, not the validator.
            if device_id in valid_device_ids or device_id == "auto" or device_id.startswith(("cuda:", "rocm:")):
                updates["PHANTOM_GRID_GPU_DEVICE"] = device_id

    if "witness_chat_tts" in payload:
        value = payload["witness_chat_tts"]
        truthy = value if isinstance(value, bool) else str(value).strip().lower() not in {"", "0", "false", "off", "no"}
        updates["PHANTOM_GRID_WITNESS_CHAT_TTS"] = "1" if truthy else "0"

    if updates:
        _write_env_updates(updates)
        os.environ.update(updates)

    return api_settings()


def api_llama_action(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    if payload:
        api_update_settings(payload)
    settings = load_settings()
    normalized = action.strip().lower()
    if settings.llm_provider == "external_llama_cpp_server" and normalized in {"start", "restart", "stop"}:
        llama_status, omni_status = _service_statuses(settings)
        return {
            "ok": llama_status.get("ready", False),
            "event": "External llama.cpp is user-managed. Start, restart, and stop it outside Phantom Grid.",
            "llama": llama_status,
            "omni": omni_status,
            "settings": _settings_payload(settings),
        }
    if normalized == "status":
        llama_status, omni_status = _service_statuses(settings)
        return {"ok": True, "llama": llama_status, "omni": omni_status, "settings": _settings_payload(settings)}
    if normalized == "stop":
        _stop_llama_process()
        current = load_settings()
        llama_status, omni_status = _service_statuses(current)
        return {"ok": True, "event": "MiniCPM-o service stopped.", "llama": llama_status, "omni": omni_status, "settings": _settings_payload(current)}
    if normalized == "restart":
        _stop_llama_process()
        started = _start_llama_process(settings)
        current = load_settings()
        llama_status, omni_status = _service_statuses(current)
        return {"ok": started["ok"], "event": started["event"], "llama": llama_status, "omni": omni_status, "settings": _settings_payload(current)}
    if normalized == "start":
        started = _start_llama_process(settings)
        current = load_settings()
        llama_status, omni_status = _service_statuses(current)
        return {"ok": started["ok"], "event": started["event"], "llama": llama_status, "omni": omni_status, "settings": _settings_payload(current)}
    llama_status, omni_status = _service_statuses(settings)
    return {"ok": False, "event": f"Unknown llama action: {action}", "llama": llama_status, "omni": omni_status, "settings": _settings_payload(settings)}


def api_omni_status() -> dict[str, Any]:
    settings = load_settings()
    health = OmniClient(settings).omni_health()
    return _omni_status_payload(settings, health)


def _service_statuses(settings) -> tuple[dict[str, Any], dict[str, Any]]:
    client = OmniClient(settings)
    return _llama_status(settings, client.health()), _omni_status_payload(settings, client.omni_health())


def _omni_status_payload(settings, health: dict[str, Any]) -> dict[str, Any]:
    scan = scan_minicpm_models(settings.minicpm_model_dir)
    managed = bool(
        settings.llm_provider == "minicpm_omni"
        and _LLAMA_PROCESS
        and _LLAMA_PROCESS.poll() is None
    )
    return {
        "ok": True,
        "reachable": health.get("reachable", False),
        "ready": health.get("ready", False),
        "detail": health.get("detail"),
        "managed_process": managed,
        "pid": _LLAMA_PROCESS.pid if managed else None,
        "model_complete": scan.get("complete", False),
        "selected_model": settings.minicpm_quantization,
        "context_length": settings.llamacpp_context_length,
        "gpu_layers": settings.llamacpp_gpu_layers,
    }


def api_omni_models() -> dict[str, Any]:
    settings = load_settings()
    return {"ok": True, **scan_minicpm_models(settings.minicpm_model_dir)}


def api_setup_status() -> dict[str, Any]:
    global _SETUP_PROCESS
    paths = _local_runtime_paths()
    scan = scan_minicpm_models(paths["models"])
    files_ready = (
        (paths["comni"] / "worker.py").exists()
        and (paths["comni"] / "gateway.py").exists()
        and _local_comni_python(paths["comni"]).exists()
        and _local_llama_server(paths["llama"]) is not None
        and scan.get("complete", False)
    )
    if _SETUP_PROCESS is not None and _SETUP_PROCESS.poll() is not None:
        _SETUP_PROCESS = None
    status = _read_setup_status()
    if files_ready:
        _configure_local_runtime(scan)
        health = OmniClient(load_settings()).health()
        service_ready = bool(health.get("ready"))
        return {
            "ok": True,
            "state": "ready" if service_ready else "installed",
            "stage": "ready" if service_ready else "service",
            "message": "Local AI is ready." if service_ready else "Local AI is installed and ready to start.",
            "progress": 100,
            "files_ready": True,
            "service_ready": service_ready,
            "installing": False,
        }
    return {
        "ok": status.get("state") != "error",
        "state": status.get("state", "missing"),
        "stage": status.get("stage", "setup"),
        "message": status.get("message", "Preparing the local AI runtime..."),
        "progress": int(status.get("progress", 0)),
        "files_ready": False,
        "service_ready": False,
        "installing": _setup_pid_running(),
    }


def api_setup_start(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global _SETUP_PROCESS
    # Persist any picker choices before kicking off setup so the provisioner
    # and the launcher both see the chosen model/GPU/context.
    if payload:
        api_update_settings(payload)
    current = api_setup_status()
    if current["files_ready"]:
        started = _start_llama_process(load_settings())
        return {**api_setup_status(), "event": started["event"], "ok": started["ok"]}
    if _SETUP_PROCESS is not None and _SETUP_PROCESS.poll() is None:
        return current
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    (RUNTIME_ROOT / "setup_status.json").write_text(
        json.dumps({"state": "running", "stage": "setup", "message": "Starting local AI setup...", "progress": 1}) + "\n",
        encoding="utf-8",
    )
    provisioner = PROJECT_ROOT / "scripts" / "provision_local_runtime.py"
    log = (RUNTIME_ROOT / "provisioner.log").open("a", encoding="utf-8")
    settings = load_settings()
    catalog_ids = {item["id"] for item in quantization_catalog()}
    model_file = settings.minicpm_quantization if settings.minicpm_quantization in catalog_ids else "MiniCPM-o-4_5-Q4_K_M.gguf"
    try:
        _SETUP_PROCESS = subprocess.Popen(
            [
                sys.executable,
                str(provisioner),
                "--runtime-root", str(RUNTIME_ROOT),
                "--model-file", model_file,
            ],
            cwd=PROJECT_ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except OSError as exc:
        log.close()
        return {**current, "ok": False, "state": "error", "message": f"Could not start setup: {exc}"}
    return {**api_setup_status(), "event": "Local AI setup started."}


def api_runtime_options() -> dict[str, Any]:
    settings = load_settings()
    return {
        "ok": True,
        "devices": detect_devices(),
        "quantizations": quantization_catalog(),
        "gpu_layer_presets": gpu_layer_presets(),
        "context_length_presets": context_length_presets(),
        "current": {
            "minicpm_quantization": settings.minicpm_quantization or "MiniCPM-o-4_5-Q4_K_M.gguf",
            "minicpm_gpu_device": settings.minicpm_gpu_device or "auto",
            "llamacpp_gpu_layers": settings.llamacpp_gpu_layers or "auto",
            "llamacpp_context_length": settings.llamacpp_context_length,
        },
    }


def _local_runtime_paths() -> dict[str, Path]:
    return {
        "comni": RUNTIME_ROOT / "MiniCPM-o-Demo",
        "llama": RUNTIME_ROOT / "llama.cpp-omni",
        "models": RUNTIME_ROOT / "models" / "MiniCPM-o-4_5-gguf",
    }


def _read_setup_status() -> dict[str, Any]:
    path = RUNTIME_ROOT / "setup_status.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _setup_pid_running() -> bool:
    lock_path = RUNTIME_ROOT / "setup.worker.lock"
    if lock_path.exists() and os.name == "nt":
        import msvcrt

        handle = lock_path.open("r+b")
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            handle.close()
            return True
        handle.close()
    path = RUNTIME_ROOT / "setup.pid"
    if not path.exists():
        return False
    try:
        pid = int(path.read_text(encoding="ascii").strip())
        if os.name == "nt":
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                raise OSError(f"Process {pid} is not running.")
            ctypes.windll.kernel32.CloseHandle(handle)
        else:
            os.kill(pid, 0)
        return True
    except (OSError, SystemError, ValueError):
        path.unlink(missing_ok=True)
        return False


def _local_llama_server(root: Path) -> Path | None:
    candidates = (
        root / "build" / "bin" / "Release" / "llama-omni-server.exe",
        root / "build" / "bin" / "llama-omni-server.exe",
        root / "build" / "bin" / "llama-omni-server",
        root / "build" / "bin" / "Release" / "llama-server.exe",
        root / "build" / "bin" / "llama-server.exe",
        root / "build" / "bin" / "llama-server",
    )
    return next((path for path in candidates if path.exists()), None)


def _local_comni_python(root: Path) -> Path:
    if os.name == "nt":
        return root / ".venv" / "base" / "Scripts" / "python.exe"
    return root / ".venv" / "base" / "bin" / "python"


def _configure_local_runtime(scan: dict[str, Any]) -> None:
    paths = _local_runtime_paths()
    models = scan.get("models", [])
    if not models:
        return
    current = load_settings()
    on_disk = {item["filename"]: item for item in models}
    # Honor the picker's choice if the file is on disk; otherwise fall back to
    # Q4_K_M (the default), then to whatever's available.
    preferred = (
        on_disk.get(current.minicpm_quantization)
        or next((item for item in models if "Q4_K_M" in item["filename"]), models[0])
    )
    updates = {
        "PHANTOM_GRID_OMNI_LAUNCHER_PATH": str(PROJECT_ROOT / "scripts" / "launch_minicpm_omni.py"),
        "PHANTOM_GRID_COMNI_CHECKOUT_PATH": str(paths["comni"]),
        "PHANTOM_GRID_LLAMACPP_OMNI_ROOT": str(paths["llama"]),
        "PHANTOM_GRID_MINICPM_MODEL_DIR": str(paths["models"]),
        "PHANTOM_GRID_MINICPM_QUANTIZATION": preferred["filename"],
    }
    if (
        current.comni_checkout_path == paths["comni"]
        and current.llamacpp_omni_root == paths["llama"]
        and current.minicpm_model_dir == paths["models"]
        and current.minicpm_quantization == preferred["filename"]
    ):
        return
    _write_env_updates(updates)
    os.environ.update(updates)


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
        "case_introduction": state.case_introduction if state else None,
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
        "notes": state.user_notes if state else "",
        "last_notice_text": state.last_notice_text if state else DEFAULT_NOTICE,
        "story_available": bool(state and (state.result or state.finalized_reason)),
    }


def _visible_game_state(state: GameState | None) -> dict[str, Any] | None:
    if state is None:
        return None
    confirmed_sightings = [
        sighting for sighting in state.case_introduction.get("last_seen", [])
        if sighting.get("confidence") == "confirmed"
    ]
    last_seen = confirmed_sightings[-1] if confirmed_sightings else None
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
        "last_seen": last_seen,
        "finalized_reason": state.finalized_reason,
        "effective_context_length": state.effective_context_length,
    }


def _map_payload() -> dict[str, Any]:
    metadata = load_map_metadata()
    return {
        "layers": list(metadata.get("images", {}).keys()),
        "default_layer": "normal",
        "junctions": _junction_records(),
        "atlas": public_atlas_payload(),
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
    if state is None:
        return {"raised": False, "witness_count": 0, "review_allowed": False, "notice": None}
    batch = next((item for item in reversed(state.witness_batches) if item.notice_id.startswith("notice_")), None)
    if batch is None:
        return {"raised": False, "witness_count": 0, "review_allowed": False, "notice": None}
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
    distribution: dict[int, dict[str, Any]] = {}
    for batch in state.witness_batches:
        for witness in batch.witnesses:
            location = distribution.setdefault(
                witness.junction_id,
                {
                    "junction_id": witness.junction_id,
                    "count": 0,
                    "reports": [],
                    "inspectable": False,
                    "sample_witness_id": witness.witness_id,
                    "sample_style": witness.personality.get("style", "witness"),
                    "sample_summary": witness.current_summary,
                    "sample_relevance": witness.relevance_score,
                    "viewed": False,
                },
            )
            location["count"] += 1
            location["reports"].append(
                {
                    "id": witness.witness_id,
                    "viewed": witness.witness_id in state.viewed_witness_ids,
                    "style": witness.personality.get("style", "witness"),
                    "summary": witness.current_summary,
                    "relevance": witness.relevance_score,
                    "name": witness.name,
                    "occupation": witness.occupation,
                }
            )
            location["inspectable"] = location["inspectable"] or batch.individual_review_allowed
            is_viewed = witness.witness_id in state.viewed_witness_ids
            location["viewed"] = location["viewed"] or is_viewed
            if witness.relevance_score > location["sample_relevance"]:
                location["sample_witness_id"] = witness.witness_id
                location["sample_style"] = witness.personality.get("style", "witness")
                location["sample_summary"] = witness.current_summary
                location["sample_relevance"] = witness.relevance_score
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
                    "name": witness.name,
                    "occupation": witness.occupation,
                    "voice_id": witness.voice_id,
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
        "llm_provider": settings.llm_provider,
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
        "omni_gateway_url": settings.omni_gateway_url,
        "omni_launcher_path": str(settings.omni_launcher_path or ""),
        "omni_launcher_exists": bool(settings.omni_launcher_path and settings.omni_launcher_path.exists()),
        "comni_checkout_path": str(settings.comni_checkout_path or ""),
        "llamacpp_omni_root": str(settings.llamacpp_omni_root or ""),
        "minicpm_model_dir": str(settings.minicpm_model_dir or ""),
        "minicpm_quantization": settings.minicpm_quantization,
        "llamacpp_context_length": settings.llamacpp_context_length,
        "llamacpp_gpu_layers": settings.llamacpp_gpu_layers,
        "minicpm_gpu_device": settings.minicpm_gpu_device,
        "witness_chat_tts": settings.witness_chat_tts,
        "witness_voice_dir": str(settings.witness_voice_dir),
    }


def _difficulty_from_settings(settings) -> str:
    if settings.max_turns >= 16 or settings.checks_per_turn >= 3:
        return "easy"
    if settings.max_turns <= 10 or settings.checks_per_turn <= 1:
        return "hard"
    return "normal"


def _llama_status(settings, health: dict[str, Any] | None = None) -> dict[str, Any]:
    global _LLAMA_PROCESS
    if _LLAMA_PROCESS is not None and _LLAMA_PROCESS.poll() is not None:
        _LLAMA_PROCESS = None
    health = health or OmniClient(settings).health()
    managed = bool(settings.llm_provider != "external_llama_cpp_server" and _LLAMA_PROCESS is not None)
    return {
        "managed_process": managed,
        "pid": _LLAMA_PROCESS.pid if managed else None,
        "reachable": health.get("reachable", False),
        "ready": health.get("ready", False),
        "detail": health.get("detail"),
    }


def _start_llama_process(settings) -> dict[str, Any]:
    global _LLAMA_PROCESS
    if _LLAMA_PROCESS is not None and _LLAMA_PROCESS.poll() is None:
        return {"ok": True, "event": f"The selected AI backend is already managed as PID {_LLAMA_PROCESS.pid}."}
    if settings.llm_provider == "external_llama_cpp_server":
        return {"ok": False, "event": "External llama.cpp is user-managed and cannot be started by Phantom Grid."}
    if settings.llm_provider == "llama_cpp_server":
        if not settings.llamacpp_server_bin or not settings.llamacpp_server_bin.is_file():
            return {"ok": False, "event": "Set a valid llama-server executable before starting."}
        if not settings.llamacpp_model_path or not settings.llamacpp_model_path.is_file():
            return {"ok": False, "event": "Set a valid GGUF model path before starting."}
        gpu_layers = "999" if settings.llamacpp_gpu_layers == "auto" else settings.llamacpp_gpu_layers
        args = [
            str(settings.llamacpp_server_bin), "-m", str(settings.llamacpp_model_path),
            "--host", "127.0.0.1", "--port", str(_port_from_base_url(settings.llamacpp_base_url)),
            "-c", str(settings.llamacpp_context_length), "-ngl", gpu_layers,
        ]
        env = os.environ.copy()
        env.update(resolve_device_env(settings.minicpm_gpu_device or "auto", settings.llamacpp_gpu_layers or "auto"))
        try:
            _LLAMA_PROCESS = subprocess.Popen(
                args,
                cwd=str(settings.llamacpp_model_path.parent),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except OSError as exc:
            return {"ok": False, "event": f"Could not start llama.cpp: {exc}"}
        return {"ok": True, "event": f"llama.cpp started {settings.llamacpp_model_path.name} as PID {_LLAMA_PROCESS.pid}."}
    if not settings.omni_launcher_path or not settings.omni_launcher_path.exists():
        return {"ok": False, "event": "Set a valid Comni launcher path before starting."}
    if not settings.comni_checkout_path or not settings.comni_checkout_path.exists():
        return {"ok": False, "event": "Set a valid OpenBMB Comni checkout directory before starting."}
    if not settings.llamacpp_omni_root or not settings.llamacpp_omni_root.exists():
        return {"ok": False, "event": "Set a valid llama.cpp-omni root directory before starting."}
    scan = scan_minicpm_models(settings.minicpm_model_dir)
    valid_names = {item["filename"] for item in scan.get("models", [])}
    if settings.minicpm_quantization not in valid_names:
        return {"ok": False, "event": "Select a detected MiniCPM-o quantization before starting."}
    if not scan.get("complete"):
        return {"ok": False, "event": "The MiniCPM-o model directory is missing required audio/TTS companion GGUF modules."}
    launcher = settings.omni_launcher_path
    suffix = launcher.suffix.lower()
    if suffix == ".ps1":
        args = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(launcher)]
    elif suffix in {".bat", ".cmd"}:
        args = ["cmd", "/c", str(launcher)]
    elif suffix == ".py":
        args = [sys.executable, str(launcher)]
    else:
        args = [str(launcher)]
    env = os.environ.copy()
    env.update({
        "MINICPM_MODEL_DIR": str(settings.minicpm_model_dir or ""),
        "MINICPM_LLM_MODEL": settings.minicpm_quantization,
        "MINICPM_CTX_SIZE": str(settings.llamacpp_context_length),
        "MINICPM_N_GPU_LAYERS": settings.llamacpp_gpu_layers,
        "MINICPM_GPU_DEVICE": settings.minicpm_gpu_device or "auto",
        "MINICPM_LLAMACPP_ROOT": str(settings.llamacpp_omni_root or ""),
        "MINICPM_GATEWAY_URL": settings.omni_gateway_url,
        "MINICPM_COMNI_ROOT": str(settings.comni_checkout_path or ""),
        "MINICPM_COMNI_PYTHON": str(_local_comni_python(settings.comni_checkout_path)) if settings.comni_checkout_path else "",
    })
    env.update(resolve_device_env(settings.minicpm_gpu_device or "auto", settings.llamacpp_gpu_layers or "auto"))
    try:
        _LLAMA_PROCESS = subprocess.Popen(
            args,
            cwd=str(launcher.parent),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except OSError as exc:
        return {"ok": False, "event": f"Could not start MiniCPM-o: {exc}"}
    return {"ok": True, "event": f"MiniCPM-o stack launcher started as PID {_LLAMA_PROCESS.pid}."}


def _stop_llama_process() -> None:
    global _LLAMA_PROCESS
    if _LLAMA_PROCESS is None:
        return
    if _LLAMA_PROCESS.poll() is None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(_LLAMA_PROCESS.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
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


def _require_omni_ready() -> None:
    health = OmniClient.from_settings().health()
    if not health.get("ready"):
        raise HTTPException(status_code=503, detail="The selected AI backend is unavailable. Start or retry it in Settings.")


def _voice_path(voice_id: str) -> Path | None:
    if not voice_id.startswith("voice_") or not voice_id[6:].isdigit():
        return None
    root = load_settings().witness_voice_dir.resolve()
    candidate = (root / f"{voice_id}.wav").resolve()
    if candidate.parent != root or not candidate.exists():
        return None
    return candidate


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
    if state is None:
        try:
            state = load_state(game_id)
            _SESSIONS[game_id] = state
        except (FileNotFoundError, KeyError, TypeError, ValueError):
            state = None
    if state is None and required:
        raise HTTPException(status_code=404, detail="Case not found. Start a new case.")
    if state is not None and ensure_case_introduction(state):
        persist(state)
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
    atlas = public_atlas_payload()
    places = [*atlas.get("districts", []), *atlas.get("landmarks", [])]
    records: list[dict[str, Any]] = []
    for junction in data.get("junctions", []):
        enriched = dict(junction)
        enriched["nearest_landmarks"] = [
            {
                "id": place.get("id"),
                "name": place.get("name"),
                "category": place.get("category"),
            }
            for place in places
            if int(junction["id"]) in {
                *place.get("junction_ids", []),
                *place.get("nearby_junction_ids", []),
                *([place["junction_id"]] if place.get("junction_id") is not None else []),
            }
        ]
        records.append(enriched)
    return records


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
