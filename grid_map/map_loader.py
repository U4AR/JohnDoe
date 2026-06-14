from __future__ import annotations

from pathlib import Path

from config import load_settings
from .storage import read_json


def load_map_metadata() -> dict:
    settings = load_settings()
    return read_json(settings.map_metadata_path)


def image_for_layer(layer: str) -> str:
    settings = load_settings()
    metadata = load_map_metadata()
    images = metadata.get("images", {})
    if layer not in images:
        raise KeyError(f"Unknown map layer: {layer}")
    path = Path(images[layer])
    if not path.is_absolute():
        path = settings.project_root / path
    return str(path)
