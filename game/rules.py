from __future__ import annotations

from config import load_settings
from .state import JunctionCheck


def can_review_individual_witnesses(total_witnesses: int) -> bool:
    return total_witnesses <= load_settings().individual_witness_threshold


def checks_remaining_this_turn(turn_number: int, checks: list[JunctionCheck | dict]) -> int:
    settings = load_settings()
    used = 0
    for check in checks:
        check_turn = check.get("turn_number") if isinstance(check, dict) else check.turn_number
        if check_turn == turn_number:
            used += 1
    return max(settings.checks_per_turn - used, 0)
