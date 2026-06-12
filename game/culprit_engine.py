from __future__ import annotations

from dataclasses import asdict

from grid_map.graph_loader import legal_moves_from

from .state import CulpritMove, GameState


def choose_rule_based_move(state: GameState) -> CulpritMove:
    blocks = [asdict(block) for block in state.active_blocks]
    legal_moves = [move for move in legal_moves_from(state.culprit.current_junction, blocks) if not move.blocked]
    if not legal_moves:
        return CulpritMove(
            turn_number=state.turn_number,
            from_junction=state.culprit.current_junction,
            to_junction=state.culprit.current_junction,
            mode="remain",
            route=[state.culprit.current_junction],
            risk_level="high",
        )

    checked = {check.junction_id for check in state.junction_checks[-6:]}
    notice_junctions = {
        int(plan["junction_id"])
        for notice in state.notices[-3:]
        for plan in notice.response_plan
    }

    def score(move) -> tuple[int, int, str]:
        pressure = 0
        if move.destination in checked:
            pressure += 5
        if move.destination in notice_junctions:
            pressure += 2
        mode_preference = {"subway": 0, "bus": 1, "taxi": 2}.get(move.mode, 3)
        return (pressure, mode_preference, move.mode)

    chosen = sorted(legal_moves, key=score)[0]
    risk = "low" if score(chosen)[0] == 0 else "medium"
    return CulpritMove(
        turn_number=state.turn_number,
        from_junction=state.culprit.current_junction,
        to_junction=chosen.destination,
        mode=chosen.mode,
        route=list(chosen.via),
        risk_level=risk,
    )


def apply_culprit_move(state: GameState, move: CulpritMove) -> None:
    state.culprit.current_junction = move.to_junction
    state.culprit.route_history.append(move)
    state.game_log.append(
        {
            "turn_number": state.turn_number,
            "kind": "culprit_move_private",
            "message": f"Culprit moved from {move.from_junction} to {move.to_junction} by {move.mode}.",
        }
    )
