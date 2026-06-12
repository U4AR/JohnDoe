from pathlib import Path

from app import (
    _SESSIONS,
    _active_blocks_text,
    _case_state_text,
    _game_log_text,
    _witness_batches_text,
    api_check_junctions,
    build_app,
    junctions_for_drag_path,
    nearest_junction_for_point,
    new_case,
    select_junctions,
    toggle_junction_selection,
)
from config import load_settings
from game.save_load import game_dir_for, load_state
from game.session import add_block, check_junction, end_turn, issue_notice, new_game, question_witness
from grid_map.map_loader import image_for_layer


def test_map_layers_use_overlay_outputs():
    assert Path(image_for_layer("normal")).name == "junctions_labelled.png"
    assert Path(image_for_layer("taxi")).name == "graph_on_map.png"
    assert Path(image_for_layer("bus")).name == "graph_on_map.png"
    assert Path(image_for_layer("subway")).name == "graph_on_map.png"


def test_settings_use_requested_gemma_model():
    settings = load_settings()
    assert settings.llamacpp_model_path == Path(
        r"C:\Users\ashis\AppData\Roaming\VoiceKeyboard\VoiceKeyboard\config\models\unsloth__gemma-4-E4B-it-GGUF\gemma-4-E4B-it-Q4_K_M.gguf"
    )
    assert settings.llamacpp_model_path.exists()


def test_full_playable_flow_persists_files_and_ui_summaries():
    state = new_game("A nervous-looking person in a grey raincoat carrying a red folder.", 100)
    state, batch = issue_notice(state, "Look for a grey raincoat carrying something red at Junction 100.")
    batch.individual_review_allowed = True
    state, answer = question_witness(state, batch.witnesses[0].witness_id, "What did they carry?")
    state, block_message = add_block(state, "edge_block", from_junction=100, to_junction=99, mode="taxi", turns=1)
    state, check_message = check_junction(state, 101)
    state, turn_message = end_turn(state)

    assert answer
    assert "Blocked edge" in block_message
    assert check_message == "No confirmed sighting."
    assert "Turn advanced" in turn_message
    assert state.turn_number == 2
    assert state.culprit.route_history
    assert state.witness_batches[0].witnesses[0].corruption_level > 0

    game_dir = game_dir_for(state.game_id)
    assert (game_dir / "game_state.json").exists()
    assert (game_dir / "culprit_private_state.json").exists()
    assert (game_dir / "notices" / "notice_001.json").exists()
    assert (game_dir / "witnesses" / "batch_notice_001.json").exists()
    assert (game_dir / "logs" / "game_log.json").exists()

    reloaded = load_state(state.game_id)
    assert reloaded.game_id == state.game_id
    assert reloaded.turn_number == 2
    assert reloaded.witness_batches[0].witnesses[0].question_history

    assert "Turn: 2 / 12" in _case_state_text(reloaded)
    assert "batch_notice_001" in _witness_batches_text(reloaded)
    assert "No active blocks" in _active_blocks_text(reloaded)
    assert "turn_advance" in _game_log_text(reloaded)


def test_server_mode_ui_exposes_custom_routes_without_blocks_components():
    assert nearest_junction_for_point(424, 79) == 1

    app = build_app()
    route_paths = {route.path for route in app.routes}
    assert type(app).__name__ == "Server"
    assert "/" in route_paths
    assert "/api/new_case" in route_paths
    assert "/assets/maps/{layer}" in route_paths
    assert not app.blocks


def test_api_snapshot_hides_culprit_and_exposes_map_context():
    snapshot = new_case("A nervous-looking person in a grey raincoat carrying a red folder.")
    game_id = snapshot["game"]["game_id"]

    assert game_id in _SESSIONS
    assert "culprit" not in snapshot["game"]
    assert snapshot["map"]["junctions"]
    assert snapshot["asset_prompts"]["suspect_placeholder"]

    selected = select_junctions(game_id, [100, 99], 100)
    assert selected["selection"]["focused"] == 100
    assert selected["selection"]["legal_moves"]


def test_default_lookout_without_selection_creates_map_witness_reports():
    from app import api_issue_notice

    snapshot = new_case("A nervous-looking person in a grey raincoat carrying a red folder.")
    notice = api_issue_notice(
        snapshot["game"]["game_id"],
        "Look for a nervous person in a grey raincoat carrying something red near the selected junction.",
        [],
        None,
    )

    assert notice["selection"]["focused"] == 100
    assert notice["lookout"]["raised"] is True
    assert notice["witness_locations"]
    assert "sample_summary" in notice["witness_locations"][0]


def test_multi_junction_selection_and_drag_helpers():
    selected = toggle_junction_selection([], 100)
    selected = toggle_junction_selection(selected, 99)
    selected = toggle_junction_selection(selected, 100)

    assert selected == [99]
    dragged = junctions_for_drag_path([{"x": 424, "y": 79}, {"x": 949, "y": 69}])
    assert 1 in dragged
    assert 2 in dragged


def test_multi_check_uses_focused_junction_first():
    snapshot = new_case("A nervous-looking person in a grey raincoat carrying a red folder.")
    game_id = snapshot["game"]["game_id"]
    state = _SESSIONS[game_id]
    state.culprit.current_junction = 100

    checked = api_check_junctions(game_id, [99, 100], 100)

    assert "J100: Culprit found" in checked["event"]
    assert checked["game"]["result"] == "commissioner_win"
