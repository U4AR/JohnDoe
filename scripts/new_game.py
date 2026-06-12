from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import load_settings
from game.state import CulpritState, GameState
from grid_map.storage import write_json


def create_new_game(initial_description: str, starting_junction: int = 100) -> Path:
    settings = load_settings()
    game_id = datetime.now().strftime("game_%Y%m%d_%H%M%S")
    game_dir = settings.games_dir / game_id
    state = GameState(
        game_id=game_id,
        turn_number=1,
        max_turns=settings.max_turns,
        phase="commissioner_action",
        initial_description=initial_description,
        culprit=CulpritState(
            current_junction=starting_junction,
            current_disguise=initial_description,
            remaining_disguise_changes=settings.starting_disguise_changes,
        ),
    )
    write_json(game_dir / "game_state.json", state.to_dict())
    write_json(game_dir / "culprit_private_state.json", state.culprit.__dict__)
    for subdir in ("notices", "witnesses", "turns", "logs"):
        (game_dir / subdir).mkdir(parents=True, exist_ok=True)
    return game_dir


if __name__ == "__main__":
    path = create_new_game("A nervous-looking person in a grey raincoat carrying a red folder.")
    print(f"Created {path}")
