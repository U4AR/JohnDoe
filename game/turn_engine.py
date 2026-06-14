from __future__ import annotations

from .police_actions import tick_blocks
from .state import GameState, JunctionCheck
from .story_engine import apply_turn_bundle, generate_turn_bundle
from .witness_engine import corrupt_witnesses_slightly, generate_ambient_witness_batch
from .win_conditions import apply_junction_check, culprit_has_escaped


def advance_turn(state: GameState, use_model: bool = False) -> str:
    if state.result:
        return "Game is already complete."

    pre_catch = _search_team_catch(state, phase="stakeout")
    if pre_catch is not None:
        return _finalize_capture(state, pre_catch, "A search team was already watching this junction when the turn opened.")

    move, story, witnesses, venues = generate_turn_bundle(state, use_model=use_model)
    apply_turn_bundle(state, move, story, witnesses, venues)
    ambient_batch = generate_ambient_witness_batch(state, [witness.potential_id for witness in witnesses])
    if ambient_batch:
        state.witness_batches.append(ambient_batch)
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

    post_catch = _search_team_catch(state, phase="intercept")
    if post_catch is not None:
        return _finalize_capture(state, post_catch, "A search team intercepted the culprit after their move.")

    if culprit_has_escaped(state):
        state.result = "culprit_escape"
        state.phase = "complete"
        message = "The culprit avoided detection until the turn limit expired."
    else:
        message = f"Turn advanced. Public report: no confirmed capture. Turns remaining: {state.max_turns - state.turn_number + 1}."
    if ambient_batch:
        message += f" {ambient_batch.total_witnesses} new witness report(s) surfaced across the city."

    state.game_log.append({"turn_number": state.turn_number, "kind": "turn_advance", "message": message})
    return message


def _search_team_catch(state: GameState, phase: str) -> int | None:
    search_team_junctions = {t.junction_id for t in state.placed_tactics if t.tactic_type == "search_team"}
    if state.culprit.current_junction in search_team_junctions:
        return state.culprit.current_junction
    return None


def _finalize_capture(state: GameState, junction_id: int, reason: str) -> str:
    apply_junction_check(state, junction_id)
    check_id = f"check_t{state.turn_number:03d}_search_team"
    state.junction_checks.append(JunctionCheck(
        check_id=check_id,
        turn_number=state.turn_number,
        junction_id=junction_id,
        result="culprit_found",
    ))
    message = f"Commissioner wins. {reason} Junction {junction_id} secured."
    state.game_log.append({"turn_number": state.turn_number, "kind": "turn_advance", "message": message})
    return message
