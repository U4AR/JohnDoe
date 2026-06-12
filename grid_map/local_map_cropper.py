from __future__ import annotations

from pathlib import Path


def planned_crop_path(game_id: str, turn_number: int, junction_id: int, output_dir: Path) -> Path:
    return output_dir / game_id / "map_crops" / f"turn_{turn_number:03d}_j{junction_id}.png"

