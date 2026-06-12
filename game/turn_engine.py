from __future__ import annotations

from .culprit_engine import apply_culprit_move, choose_rule_based_move
from .police_actions import tick_blocks
from .state import GameState
from .witness_engine import corrupt_witnesses_slightly
from .win_conditions import culprit_has_escaped


def advance_turn(state: GameState) -> str:
    if state.result:
        return "Game is already complete."

    move = choose_rule_based_move(state)
    apply_culprit_move(state, move)
    corrupt_witnesses_slightly(state)
    state.active_blocks = tick_blocks(state.active_blocks)
    active_block_ids = {block.block_id for block in state.active_blocks}
    state.placed_tactics = [
        tactic
        for tactic in state.placed_tactics
        if tactic.linked_block_id is None or tactic.linked_block_id in active_block_ids
    ]
    state.turn_number += 1
    state.phase = "commissioner_action"

    if culprit_has_escaped(state):
        state.result = "culprit_escape"
        state.phase = "complete"
        message = "The culprit avoided detection until the turn limit expired."
    else:
        message = f"Turn advanced. Public report: no confirmed capture. Turns remaining: {state.max_turns - state.turn_number + 1}."

    state.game_log.append({"turn_number": state.turn_number, "kind": "turn_advance", "message": message})
    return message
