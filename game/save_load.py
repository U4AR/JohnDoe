from __future__ import annotations

from pathlib import Path
from typing import Any

from config import load_settings
from .state import GameState
from grid_map.storage import read_json, write_json


def game_dir_for(game_id: str) -> Path:
    return load_settings().games_dir / game_id


def save_game_state(game_dir: Path, state: dict[str, Any] | GameState) -> None:
    data = state.to_dict() if isinstance(state, GameState) else state
    game_dir.mkdir(parents=True, exist_ok=True)
    write_json(game_dir / "game_state.json", data)
    culprit = data.get("culprit", {})
    write_json(game_dir / "culprit_private_state.json", culprit)
    for notice in data.get("notices", []):
        write_json(game_dir / "notices" / f"{notice['notice_id']}.json", notice)
    for batch in data.get("witness_batches", []):
        write_json(game_dir / "witnesses" / f"{batch['batch_id']}.json", batch)
    write_json(game_dir / "logs" / "game_log.json", data.get("game_log", []))


def load_game_state(game_dir: Path) -> dict[str, Any]:
    return read_json(game_dir / "game_state.json")


def load_state(game_id: str) -> GameState:
    return GameState.from_dict(load_game_state(game_dir_for(game_id)))
