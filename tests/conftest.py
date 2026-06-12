from __future__ import annotations

import shutil

import pytest

from config import load_settings


@pytest.fixture(autouse=True)
def clean_generated_games():
    games_dir = load_settings().games_dir
    games_dir.mkdir(parents=True, exist_ok=True)
    for child in games_dir.iterdir():
        if child.is_dir() and child.name.startswith("game_"):
            shutil.rmtree(child)
    yield
    for child in games_dir.iterdir():
        if child.is_dir() and child.name.startswith("game_"):
            shutil.rmtree(child)
