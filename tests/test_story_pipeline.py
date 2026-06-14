from pathlib import Path

import pytest

from game.context_budget import ContextBudget, normalize_context_length
from game.session import end_turn, issue_notice, new_game
from game.state import PlacedTactic
from game.story_engine import _validated_decision, ensure_case_introduction
from game.witness_engine import answer_witness_question, generate_ambient_witness_batch
from grid_map.graph_loader import legal_moves_from
from llm.omni_client import scan_minicpm_models


def test_context_budget_scales_and_validates():
    small = ContextBudget.for_context(4096)
    large = ContextBudget.for_context(32768)

    assert small.output_tokens < large.output_tokens
    assert small.recent_story_segments < large.recent_story_segments
    assert small.recent_interview_turns < large.recent_interview_turns
    assert normalize_context_length(8500) == 8192
    with pytest.raises(ValueError):
        normalize_context_length(2048)


def test_turn_story_matches_the_committed_decision_and_witness_facts():
    state = new_game("a nervous person in a grey raincoat carrying a red folder", 100)
    opening_count = len(state.story_segments)

    state, _ = end_turn(state)

    assert len(state.story_segments) == opening_count + 1
    move = state.culprit.route_history[-1]
    story = state.story_segments[-1]
    assert (story.from_junction, story.to_junction, story.mode, story.route) == (
        move.from_junction,
        move.to_junction,
        move.mode,
        move.route,
    )
    fact_ids = {fact.fact_id for fact in story.observable_facts}
    turn_witnesses = [
        item for item in state.potential_witnesses if set(item.observed_fact_ids) & fact_ids
    ]
    assert turn_witnesses
    assert all(set(witness.observed_fact_ids) <= fact_ids for witness in turn_witnesses)


def test_turn_can_surface_route_and_city_witness_reports():
    state = new_game("a nervous person in a grey raincoat carrying a red folder", 100)

    class FixedRandom:
        def __init__(self, seed): pass
        def random(self): return 0.01
        def randrange(self, size): return 0
        def choice(self, values): return values[0]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("game.witness_engine.random.Random", FixedRandom)
        state, message = end_turn(state)

    ambient = [batch for batch in state.witness_batches if batch.notice_id.startswith("ambient_t")]
    assert "Turn advanced" in message
    assert ambient
    assert any(not witness.is_false_positive for witness in ambient[-1].witnesses)
    assert any(witness.is_false_positive for witness in ambient[-1].witnesses)
    route = set(state.culprit.route_history[-1].route)
    assert any(witness.junction_id in route for witness in ambient[-1].witnesses if not witness.is_false_positive)


def test_each_turn_guarantees_an_off_route_city_report(monkeypatch):
    state = new_game("a nervous person in a grey raincoat carrying a red folder", 100)
    route_potential = next(item for item in state.potential_witnesses if item.junction_id == 100)

    class FixedRandom:
        def __init__(self, seed): pass
        def random(self): return 0.99
        def randrange(self, size): return 0
        def choice(self, values): return values[0]

    monkeypatch.setattr("game.witness_engine.random.Random", FixedRandom)
    batch = generate_ambient_witness_batch(state, [route_potential.potential_id])

    assert batch is not None
    city_reports = [witness for witness in batch.witnesses if witness.is_false_positive]
    assert city_reports
    assert all(witness.junction_id != route_potential.junction_id for witness in city_reports)


def test_matching_lookout_board_greatly_boosts_correct_route_witness(monkeypatch):
    state = new_game("a nervous person in a grey raincoat carrying a red folder", 100)
    state, _ = issue_notice(state, "grey raincoat carrying a red folder", anchor_junction=100)
    state.placed_tactics.append(PlacedTactic("board", "lookout_board", 1, 100, 0, 0))
    potential = next(item for item in state.potential_witnesses if item.junction_id == 100)
    potential.surfaced_notice_id = None

    class FixedRandom:
        def __init__(self, seed): pass
        def random(self): return 0.9
        def randrange(self, size): return 0
        def choice(self, values): return values[0]

    monkeypatch.setattr("game.witness_engine.random.Random", FixedRandom)
    batch = generate_ambient_witness_batch(state, [potential.potential_id])

    assert batch is not None
    assert any(not witness.is_false_positive for witness in batch.witnesses)


def test_new_game_builds_a_public_case_introduction_and_sighting_trail():
    state = new_game("a nervous person in a grey raincoat carrying a red folder", 100)

    intro = state.case_introduction
    assert intro["case_title"]
    assert intro["culprit_alias"]
    assert intro["crime"]
    assert intro["stolen_item"]
    assert len(intro["last_seen"]) == 3
    assert intro["last_seen"][-1]["junction_id"] == state.culprit.current_junction
    assert intro["last_seen"][-1]["confidence"] == "confirmed"


def test_missing_case_introduction_can_be_backfilled_for_older_saves():
    state = new_game("a nervous person in a grey raincoat carrying a red folder", 100)
    state.case_introduction = {}

    assert ensure_case_introduction(state) is True
    assert state.case_introduction["case_title"]
    assert ensure_case_introduction(state) is False


def test_notice_surfaces_a_matching_witness_only_once():
    state = new_game("a nervous person in a grey raincoat carrying a red folder", 100)
    state, first = issue_notice(state, "Grey raincoat carrying a red folder near Junction 100")
    state, second = issue_notice(state, "Grey raincoat carrying a red folder near Junction 100")

    assert first.witnesses
    surfaced = {witness.witness_id for witness in first.witnesses}
    assert surfaced.isdisjoint({witness.witness_id for witness in second.witnesses})


def test_notice_response_plan_includes_the_board_anchor():
    state = new_game("a nervous person in a grey raincoat carrying a red folder", 100)
    state, batch = issue_notice(state, "Report anyone carrying a red folder", anchor_junction=50)

    notice = state.notices[-1]
    assert notice.response_plan[0]["junction_id"] == 50
    assert batch.witnesses


def test_matching_notice_returns_story_witnesses_and_coherent_false_leads():
    state = new_game("a nervous person in a grey raincoat carrying a red folder", 100)

    state, batch = issue_notice(
        state,
        "Grey raincoat carrying a red folder near Junction 100",
        anchor_junction=100,
    )

    real = [witness for witness in batch.witnesses if not witness.is_false_positive]
    false = [witness for witness in batch.witnesses if witness.is_false_positive]
    assert real
    assert false
    assert all(witness.observed_fact_ids for witness in real)
    assert all(not witness.observed_fact_ids for witness in false)
    assert all(witness.current_summary.strip() for witness in batch.witnesses)
    assert all(witness.name != "Unknown witness" for witness in batch.witnesses)
    assert all({"style", "confidence", "quirk"} <= witness.personality.keys() for witness in batch.witnesses)
    false_answer = answer_witness_question(false[0], "What were they carrying?", state.turn_number)
    assert "parcel" in false_answer.lower()


def test_unrelated_notice_returns_only_false_witnesses_at_the_selected_area():
    state = new_game("a nervous person in a grey raincoat carrying a red folder", 100)

    state, batch = issue_notice(
        state,
        "Blue helmet and green backpack near Junction 100",
        anchor_junction=100,
    )

    assert batch.witnesses
    assert all(witness.is_false_positive for witness in batch.witnesses)
    assert batch.witnesses[0].junction_id == 100


def test_generic_notice_creates_distinct_false_witnesses_with_personality_grounded_answers():
    state = new_game("a nervous person in a grey raincoat carrying a red folder", 100)

    state, batch = issue_notice(
        state,
        "Report anyone suspicious in the nearby area",
        anchor_junction=71,
    )
    false = [witness for witness in batch.witnesses if witness.is_false_positive]

    assert len(false) >= 2
    assert len({witness.name for witness in false}) == len(false)
    assert false[0].junction_id == 71
    answers = [answer_witness_question(witness, "What were they carrying?", state.turn_number) for witness in false]
    assert all(answer.strip() for answer in answers)
    assert len(set(answers)) == len(answers)


def test_notice_wording_is_required_to_surface_a_story_witness():
    state = new_game("a nervous person in a grey raincoat carrying a red folder", 100)

    state, batch = issue_notice(state, "Report a blue helmet", anchor_junction=100)

    assert all(witness.is_false_positive for witness in batch.witnesses)


def test_compact_model_action_is_accepted_when_it_matches_a_legal_move():
    state = new_game("a nervous person in a grey raincoat carrying a red folder", 100)
    moves = [move for move in legal_moves_from(100) if not move.blocked]
    selected = moves[0]

    decision = _validated_decision(
        state,
        moves,
        {"action": f"{selected.mode} to {selected.destination}"},
    )

    assert decision.to_junction == selected.destination
    assert decision.mode == selected.mode


def test_model_scan_lists_quantizations_and_requires_companions(tmp_path: Path):
    model = tmp_path / "MiniCPM-o-4_5-Q4_K_M.gguf"
    model.write_bytes(b"gguf")
    incomplete = scan_minicpm_models(tmp_path)
    assert incomplete["models"][0]["quantization"] == "Q4_K_M"
    assert incomplete["complete"] is False

    for folder in ("audio", "tts", "token2wav-gguf"):
        companion = tmp_path / folder / "module.gguf"
        companion.parent.mkdir(parents=True, exist_ok=True)
        companion.write_bytes(b"gguf")

    complete = scan_minicpm_models(tmp_path)
    assert complete["complete"] is True
