from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"


def _load_env_file() -> None:
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if not value else int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if not value else float(value)


def _env_path(name: str, default: Path | None = None) -> Path | None:
    value = os.getenv(name)
    if value:
        return Path(value)
    return default


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    raw_maps_dir: Path = PROJECT_ROOT / "data" / "raw" / "maps"
    processed_dir: Path = PROJECT_ROOT / "data" / "processed"
    games_dir: Path = PROJECT_ROOT / "data" / "games"
    junction_registry_path: Path = PROJECT_ROOT / "data" / "processed" / "junction_registry.json"
    game_graph_path: Path = PROJECT_ROOT / "data" / "processed" / "game_graph.json"
    map_metadata_path: Path = PROJECT_ROOT / "data" / "processed" / "map_metadata.json"
    map_atlas_path: Path = PROJECT_ROOT / "data" / "processed" / "map_atlas.json"

    llm_provider: str = "llama_cpp_server"
    llamacpp_server_bin: Path | None = None
    llamacpp_model_path: Path | None = None
    llamacpp_base_url: str = "http://127.0.0.1:8080/v1"
    llm_model: str = "local-gemma-4b"

    max_turns: int = 12
    checks_per_turn: int = 2
    blocks_per_turn: int = 1
    max_active_blocks: int = 3
    individual_witness_threshold: int = 12
    starting_disguise_changes: int = 3
    memory_corruption_per_turn: float = 0.08


def load_settings() -> Settings:
    _load_env_file()
    server_bin = _env_path("PHANTOM_GRID_LLAMACPP_SERVER_BIN")
    if server_bin is None:
        detected = shutil.which("llama-server") or shutil.which("llama-server.exe")
        server_bin = Path(detected) if detected else None

    return Settings(
        llm_provider=os.getenv("PHANTOM_GRID_LLM_PROVIDER", "llama_cpp_server"),
        llamacpp_server_bin=server_bin,
        llamacpp_model_path=_env_path("PHANTOM_GRID_LLAMACPP_MODEL_PATH"),
        llamacpp_base_url=os.getenv("PHANTOM_GRID_LLAMACPP_BASE_URL", "http://127.0.0.1:8080/v1"),
        llm_model=os.getenv("PHANTOM_GRID_LLM_MODEL", "local-gemma-4b"),
        max_turns=_env_int("PHANTOM_GRID_MAX_TURNS", 12),
        checks_per_turn=_env_int("PHANTOM_GRID_CHECKS_PER_TURN", 2),
        blocks_per_turn=_env_int("PHANTOM_GRID_BLOCKS_PER_TURN", 1),
        individual_witness_threshold=_env_int("PHANTOM_GRID_INDIVIDUAL_WITNESS_THRESHOLD", 12),
        memory_corruption_per_turn=_env_float("PHANTOM_GRID_MEMORY_CORRUPTION_PER_TURN", 0.08),
    )
