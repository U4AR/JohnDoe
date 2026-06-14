import pytest

@pytest.fixture(autouse=True)
def isolated_generated_games(tmp_path, monkeypatch):
    games_dir = tmp_path / "games"
    monkeypatch.setenv("PHANTOM_GRID_GAMES_DIR", str(games_dir))
    games_dir.mkdir(parents=True, exist_ok=True)
    yield games_dir
