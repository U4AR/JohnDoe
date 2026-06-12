from __future__ import annotations

import random
from datetime import datetime

from config import load_settings
from grid_map.graph_loader import all_junction_ids, legal_moves_from
from .notice_engine import create_lookout_notice
from .police_actions import create_edge_block, create_junction_block, create_mode_block
from .rules import checks_remaining_this_turn
from .save_load import game_dir_for, save_game_state
from .state import CulpritState, GameState, JunctionCheck, PlacedTactic, PoliceBlock, WitnessBatch
from .turn_engine import advance_turn
from .win_conditions import apply_junction_check
from .witness_engine import answer_witness_question, generate_witness_batch


TACTIC_LIMITS = {
    "roadblock": 3,
    "junction_lockdown": 3,
    "patrol_unit": 2,
    "search_team": 2,
    "lookout_board": 2,
}


def new_game(initial_description: str, starting_junction: int | None = None) -> GameState:
    settings = load_settings()
    if starting_junction is None:
        starting_junction = random.choice(all_junction_ids())
    game_id = datetime.now().strftime("game_%Y%m%d_%H%M%S_%f")
    state = GameState(
        game_id=game_id,
        turn_number=1,
        max_turns=settings.max_turns,
        phase="commissioner_action",
        initial_description=initial_description.strip(),
        culprit=CulpritState(
            current_junction=starting_junction,
            current_disguise=initial_description.strip(),
            remaining_disguise_changes=settings.starting_disguise_changes,
        ),
        game_log=[{"turn_number": 1, "kind": "new_game", "message": f"New investigation opened at turn 1."}],
    )
    persist(state)
    return state


def issue_notice(state: GameState, text: str) -> tuple[GameState, WitnessBatch]:
    notice = create_lookout_notice(state, text)
    state.notices.append(notice)
    batch = generate_witness_batch(state, notice)
    state.witness_batches.append(batch)
    state.game_log.append(
        {
            "turn_number": state.turn_number,
            "kind": "notice",
            "message": f"{notice.notice_id}: {batch.total_witnesses} witnesses responded.",
        }
    )
    persist(state)
    return state, batch


def check_junction(state: GameState, junction_id: int) -> tuple[GameState, str]:
    remaining = checks_remaining_this_turn(state.turn_number, state.junction_checks)
    if remaining <= 0:
        return state, "No junction checks remain this turn."
    result = apply_junction_check(state, junction_id)
    check_id = f"check_t{state.turn_number:03d}_{len(state.junction_checks) + 1:03d}"
    state.junction_checks.append(JunctionCheck(check_id=check_id, turn_number=state.turn_number, junction_id=junction_id, result=result))
    visible = "Culprit found. Commissioner wins." if result == "culprit_found" else "No confirmed sighting."
    state.game_log.append({"turn_number": state.turn_number, "kind": "junction_check", "message": f"Checked Junction {junction_id}: {visible}"})
    persist(state)
    return state, visible


def add_block(
    state: GameState,
    block_type: str,
    junction_id: int | None = None,
    from_junction: int | None = None,
    to_junction: int | None = None,
    mode: str | None = None,
    turns: int = 1,
) -> tuple[GameState, str]:
    settings = load_settings()
    if len(state.active_blocks) >= settings.max_active_blocks:
        return state, "Maximum active blocks already reached."
    block_id = f"block_t{state.turn_number:03d}_{len(state.active_blocks) + 1:03d}"
    block = _make_block(block_id, state.turn_number, block_type, junction_id, from_junction, to_junction, mode, turns)
    state.active_blocks.append(block)
    message = describe_block(block)
    state.game_log.append({"turn_number": state.turn_number, "kind": "block", "message": message})
    persist(state)
    return state, message


def question_witness(state: GameState, witness_id: str, question: str) -> tuple[GameState, str]:
    witness = find_witness(state, witness_id)
    if witness is None:
        return state, "Witness not found."
    answer = answer_witness_question(witness, question, state.turn_number)
    if witness_id not in state.viewed_witness_ids:
        state.viewed_witness_ids.append(witness_id)
    state.game_log.append({"turn_number": state.turn_number, "kind": "witness_question", "message": f"Questioned {witness_id}."})
    persist(state)
    return state, answer


def place_tactic(state: GameState, tactic_type: str, junction_id: int, x: int, y: int) -> tuple[GameState, str]:
    if tactic_type not in TACTIC_LIMITS:
        return state, "Unknown tactic."
    if _remaining_tactic_count(state, tactic_type) <= 0:
        return state, f"No {tactic_type.replace('_', ' ')} units remain."
    if junction_id not in all_junction_ids():
        return state, "Choose a valid map junction."

    tactic_id = f"tactic_t{state.turn_number:03d}_{len(state.placed_tactics) + 1:03d}"
    linked_block_id = None
    message = f"Placed {tactic_type.replace('_', ' ')} at Junction {junction_id}."

    if tactic_type == "roadblock":
        moves = legal_moves_from(junction_id, [block.__dict__ for block in state.active_blocks])
        open_move = next((move for move in moves if not move.blocked), None)
        if open_move is None:
            return state, "No open route is available for a roadblock here."
        state, message = add_block(
            state,
            "edge_block",
            from_junction=junction_id,
            to_junction=open_move.destination,
            mode=open_move.mode,
            turns=2,
        )
        linked_block_id = state.active_blocks[-1].block_id if state.active_blocks else None
    elif tactic_type == "junction_lockdown":
        state, message = add_block(state, "junction_block", junction_id=junction_id, turns=2)
        linked_block_id = state.active_blocks[-1].block_id if state.active_blocks else None

    state.placed_tactics.append(
        PlacedTactic(
            tactic_id=tactic_id,
            tactic_type=tactic_type,
            turn_created=state.turn_number,
            junction_id=junction_id,
            x=int(x),
            y=int(y),
            linked_block_id=linked_block_id,
        )
    )
    state.game_log.append({"turn_number": state.turn_number, "kind": "tactic", "message": message})
    persist(state)
    return state, message


def remove_tactic(state: GameState, tactic_id: str) -> tuple[GameState, str]:
    tactic = next((item for item in state.placed_tactics if item.tactic_id == tactic_id), None)
    if tactic is None:
        return state, "Tactic not found."
    state.placed_tactics = [item for item in state.placed_tactics if item.tactic_id != tactic_id]
    if tactic.linked_block_id:
        state.active_blocks = [block for block in state.active_blocks if block.block_id != tactic.linked_block_id]
    message = f"Removed {tactic.tactic_type.replace('_', ' ')} from Junction {tactic.junction_id}."
    state.game_log.append({"turn_number": state.turn_number, "kind": "tactic_removed", "message": message})
    persist(state)
    return state, message


def end_turn(state: GameState) -> tuple[GameState, str]:
    message = advance_turn(state)
    persist(state)
    return state, message


def persist(state: GameState) -> None:
    save_game_state(game_dir_for(state.game_id), state)


def find_witness(state: GameState, witness_id: str):
    for batch in state.witness_batches:
        for witness in batch.witnesses:
            if witness.witness_id == witness_id:
                return witness
    return None


def _remaining_tactic_count(state: GameState, tactic_type: str) -> int:
    placed = sum(1 for tactic in state.placed_tactics if tactic.tactic_type == tactic_type)
    return max(TACTIC_LIMITS[tactic_type] - placed, 0)


def describe_block(block: PoliceBlock) -> str:
    if block.block_type == "edge_block":
        mode = f" by {block.mode}" if block.mode else ""
        return f"Blocked edge {block.from_junction} -> {block.to_junction}{mode} for {block.turns_remaining} turn(s)."
    if block.block_type == "mode_block":
        scope = f" near Junction {block.junction_id}" if block.junction_id else ""
        return f"Blocked {block.mode}{scope} for {block.turns_remaining} turn(s)."
    return f"Blocked Junction {block.junction_id} for {block.turns_remaining} turn(s)."


def _make_block(
    block_id: str,
    turn_number: int,
    block_type: str,
    junction_id: int | None,
    from_junction: int | None,
    to_junction: int | None,
    mode: str | None,
    turns: int,
) -> PoliceBlock:
    if block_type == "edge_block":
        if from_junction is None or to_junction is None:
            raise ValueError("edge_block requires from_junction and to_junction")
        return create_edge_block(block_id, turn_number, from_junction, to_junction, mode, turns)
    if block_type == "mode_block":
        if not mode:
            raise ValueError("mode_block requires mode")
        return create_mode_block(block_id, turn_number, mode, junction_id, turns)
    if block_type == "junction_block":
        if junction_id is None:
            raise ValueError("junction_block requires junction_id")
        return create_junction_block(block_id, turn_number, junction_id, turns)
    raise ValueError(f"Unknown block type: {block_type}")
