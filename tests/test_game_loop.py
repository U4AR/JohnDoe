from game.session import add_block, check_junction, end_turn, issue_notice, new_game, question_witness
from grid_map.graph_loader import all_junction_ids


def test_notice_generates_witness_batch_and_threshold():
    state = new_game("A nervous-looking person in a grey raincoat carrying a red folder.", 100)
    state, batch = issue_notice(state, "Look for a grey raincoat carrying something red at Junction 100.")

    assert state.notices
    assert batch.total_witnesses > 0
    assert batch.witnesses
    assert batch.notice_id == "notice_001"


def test_correct_junction_check_wins():
    state = new_game("A nervous-looking person in a grey raincoat carrying a red folder.", 100)
    state, result = check_junction(state, 100)

    assert result == "Culprit found. Commissioner wins."
    assert state.result == "commissioner_win"


def test_block_and_advance_turn_moves_culprit_legally():
    state = new_game("A nervous-looking person in a grey raincoat carrying a red folder.", 100)
    state, _ = add_block(state, "edge_block", from_junction=100, to_junction=99, mode="taxi", turns=1)
    previous = state.culprit.current_junction
    state, message = end_turn(state)

    assert "Turn advanced" in message
    assert state.turn_number == 2
    assert state.culprit.route_history
    assert state.culprit.route_history[-1].from_junction == previous
    assert state.culprit.current_junction != 99


def test_witness_question_requires_inspectable_batch():
    state = new_game("A nervous-looking person in a grey raincoat carrying a red folder.", 100)
    state, batch = issue_notice(state, "Look for a grey raincoat carrying something red at Junction 100.")
    batch.individual_review_allowed = True
    witness_id = batch.witnesses[0].witness_id
    state, answer = question_witness(state, witness_id, "What did they carry?")

    assert answer
    assert batch.witnesses[0].question_history


def test_default_new_game_starts_at_valid_random_junction(monkeypatch):
    ids = all_junction_ids()
    chosen = ids[-1]
    monkeypatch.setattr("game.session.random.choice", lambda values: chosen)

    state = new_game("A nervous-looking person in a grey raincoat carrying a red folder.")

    assert state.culprit.current_junction == chosen
    assert state.culprit.current_junction in ids
