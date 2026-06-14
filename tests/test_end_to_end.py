from pathlib import Path

from app import (
    _SESSIONS,
    _state_for,
    _active_blocks_text,
    _case_state_text,
    _game_log_text,
    _witness_locations,
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


def test_settings_expose_minicpm_omni_configuration():
    settings = load_settings()
    assert settings.omni_gateway_url.startswith("http://127.0.0.1:")
    assert settings.omni_launcher_path.name == "launch_minicpm_omni.py"
    assert 4096 <= settings.llamacpp_context_length <= 32768
    assert settings.witness_voice_dir.exists()


def test_tests_use_isolated_game_storage(isolated_generated_games):
    settings = load_settings()

    assert settings.games_dir == isolated_generated_games
    assert settings.games_dir != settings.project_root / "data" / "games"


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
    assert "/api/setup/status" in route_paths
    assert "/api/setup/start" in route_paths
    assert not app.blocks


def test_colocated_witnesses_and_tactics_render_as_separate_click_targets():
    script = (Path(__file__).parents[1] / "ui" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    styles = (Path(__file__).parents[1] / "ui" / "web" / "static" / "app.css").read_text(encoding="utf-8")
    html = (Path(__file__).parents[1] / "ui" / "web" / "index.html").read_text(encoding="utf-8")

    assert 'token.style.setProperty("--token-offset-x", `${offset.x}px`)' in script
    assert 'token.style.setProperty("--token-offset-y", `${offset.y}px`)' in script
    assert "const colocatedWithWitness = witnessJunctions.has(placed.junction_id)" in script
    assert "calc(-50% + var(--token-offset-x, 0px))" in styles
    assert 'new URLSearchParams(window.location.search).get("game_id")' in script
    assert "showOpeningForFreshCase(snapshot)" in script
    assert "snapshot.game.turn !== 1" in script
    assert 'id="wantedLastSeen"' in html
    assert "game.last_seen?.location" in script
    assert 'id="witnessModeButton"' in html
    assert "witnessReportOffset" in script
    assert "report.id ||" in script
    assert "20260614-complete-icons-v3" in script
    assert "witness-cluster-token" in script
    assert "showWitnessClusterPopup" in script
    assert "data-action=\"open-witness\"" in script
    assert "witness-cluster-member" in script
    assert 'pin_unviewed_witness.png" : "pin_viewed_witness.png' in script


def test_tactic_map_pins_are_normalized_transparent_assets():
    from PIL import Image

    asset_dir = Path(__file__).parents[1] / "ui" / "web" / "static" / "assets" / "reference"
    for name in (
        "icon_roadblock.png",
        "icon_junction_lockdown.png",
        "icon_patrol_unit.png",
        "icon_search_team.png",
        "icon_lookout_board.png",
        "pin_roadblock.png",
        "pin_junction_lockdown.png",
        "pin_patrol_unit.png",
        "pin_search_team.png",
        "pin_lookout_board.png",
        "pin_unviewed_witness.png",
        "pin_viewed_witness.png",
    ):
        with Image.open(asset_dir / name) as image:
            assert image.size == (128, 128)
            assert image.mode == "RGBA"
            assert image.getpixel((0, 0))[3] == 0


def test_witness_map_keeps_locations_from_all_lookout_notices():
    state = new_game("A nervous person in a grey raincoat carrying a red folder.", starting_junction=100)
    state, _ = issue_notice(state, "Grey raincoat with a red folder", anchor_junction=71)
    state, _ = issue_notice(state, "Grey raincoat with a red folder", anchor_junction=83)

    locations = _witness_locations(state)

    assert {location["junction_id"] for location in locations} >= {71, 83}
    assert all(location["reports"] for location in locations)
    assert all(report["id"] for location in locations for report in location["reports"])
    report_ids = [report["id"] for location in locations for report in location["reports"]]
    assert len(report_ids) == len(set(report_ids))


def test_api_snapshot_hides_culprit_and_exposes_map_context():
    snapshot = new_case("A nervous-looking person in a grey raincoat carrying a red folder.")
    game_id = snapshot["game"]["game_id"]

    assert game_id in _SESSIONS
    assert "culprit" not in snapshot["game"]
    assert snapshot["case_introduction"]["culprit_alias"]
    assert len(snapshot["case_introduction"]["last_seen"]) == 3
    assert snapshot["game"]["last_seen"]["confidence"] == "confirmed"
    assert snapshot["game"]["last_seen"]["junction_id"] != _SESSIONS[game_id].culprit.current_junction
    assert snapshot["game"]["suspect_image"].startswith("/static/assets/suspects/")
    assert snapshot["map"]["junctions"]
    assert any(junction["nearest_landmarks"] for junction in snapshot["map"]["junctions"])
    assert snapshot["asset_prompts"]["suspect_placeholder"]

    selected = select_junctions(game_id, [100, 99], 100)
    assert selected["selection"]["focused"] == 100
    assert selected["selection"]["legal_moves"]


def test_saved_case_is_rehydrated_after_memory_state_is_cleared():
    snapshot = new_case("A nervous-looking person in a grey raincoat carrying a red folder.")
    game_id = snapshot["game"]["game_id"]
    _SESSIONS.pop(game_id)

    restored = _state_for(game_id)

    assert restored is not None
    assert restored.game_id == game_id


def test_default_lookout_without_selection_creates_map_witness_reports():
    from app import api_issue_notice

    snapshot = new_case("A nervous-looking person in a grey raincoat carrying a red folder.")
    notice = api_issue_notice(
        snapshot["game"]["game_id"],
        "Look for a nervous person in a grey raincoat carrying something red near the selected junction.",
        [],
        None,
    )

    assert notice["selection"]["focused"] == snapshot["game"]["last_seen"]["junction_id"]
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
