from __future__ import annotations

from .state import GameState


def apply_junction_check(state: GameState, junction_id: int) -> str:
    if state.culprit.current_junction == junction_id:
        state.result = "commissioner_win"
        state.phase = "complete"
        return "culprit_found"
    return "no_confirmed_sighting"


def culprit_has_escaped(state: GameState) -> bool:
    return state.turn_number >= state.max_turns and state.result is None

