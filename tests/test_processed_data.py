from pathlib import Path

from config import load_settings
from grid_map.graph_loader import legal_moves_from
from grid_map.storage import read_json


def test_processed_files_exist():
    settings = load_settings()
    assert settings.junction_registry_path.exists()
    assert settings.game_graph_path.exists()
    assert settings.map_atlas_path.exists()


def test_junction_100_has_legal_moves():
    moves = legal_moves_from(100)
    assert moves
    assert all(move.destination != 100 for move in moves)


def test_map_atlas_schema_is_ready():
    settings = load_settings()
    atlas = read_json(settings.map_atlas_path)
    assert atlas["schema_version"] == 1
    assert "landmarks" in atlas


def test_processed_metadata_images_exist():
    settings = load_settings()
    metadata = read_json(settings.map_metadata_path)
    for path in metadata["images"].values():
        assert Path(path).exists()
