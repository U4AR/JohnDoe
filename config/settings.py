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

    llm_provider: str = "minicpm_omni"
    llamacpp_server_bin: Path | None = None
    llamacpp_model_path: Path | None = None
    llamacpp_base_url: str = "http://127.0.0.1:8080/v1"
    llm_model: str = "MiniCPM-o-4_5"
    omni_gateway_url: str = "http://127.0.0.1:8006"
    omni_launcher_path: Path | None = PROJECT_ROOT / "scripts" / "launch_minicpm_omni.py"
    comni_checkout_path: Path | None = None
    llamacpp_omni_root: Path | None = None
    minicpm_model_dir: Path | None = None
    minicpm_quantization: str = ""
    llamacpp_context_length: int = 8192
    llamacpp_gpu_layers: str = "auto"
    minicpm_gpu_device: str = "auto"
    # MiniCPM-o's TTS branch routes through the audio_assistant template, which
    # makes the model freeform-respond in the speaker's voice rather than read
    # English text verbatim. Its training prior is overwhelmingly Chinese, so
    # the audio comes out Chinese even when the chat text is English. Default
    # the toggle OFF — users get sub-second English replies; flipping it on is
    # opt-in and currently expected to produce Chinese audio.
    witness_chat_tts: bool = False
    witness_voice_dir: Path = PROJECT_ROOT / "data" / "voices"

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
        games_dir=_env_path("PHANTOM_GRID_GAMES_DIR", PROJECT_ROOT / "data" / "games") or PROJECT_ROOT / "data" / "games",
        llm_provider=os.getenv("PHANTOM_GRID_LLM_PROVIDER", "minicpm_omni"),
        llamacpp_server_bin=server_bin,
        llamacpp_model_path=_env_path("PHANTOM_GRID_LLAMACPP_MODEL_PATH"),
        llamacpp_base_url=os.getenv("PHANTOM_GRID_LLAMACPP_BASE_URL", "http://127.0.0.1:8080/v1"),
        llm_model=os.getenv("PHANTOM_GRID_LLM_MODEL", "MiniCPM-o-4_5"),
        omni_gateway_url=os.getenv("PHANTOM_GRID_OMNI_GATEWAY_URL", "http://127.0.0.1:8006"),
        omni_launcher_path=_env_path("PHANTOM_GRID_OMNI_LAUNCHER_PATH", PROJECT_ROOT / "scripts" / "launch_minicpm_omni.py"),
        comni_checkout_path=_env_path("PHANTOM_GRID_COMNI_CHECKOUT_PATH"),
        llamacpp_omni_root=_env_path("PHANTOM_GRID_LLAMACPP_OMNI_ROOT"),
        minicpm_model_dir=_env_path("PHANTOM_GRID_MINICPM_MODEL_DIR"),
        minicpm_quantization=os.getenv("PHANTOM_GRID_MINICPM_QUANTIZATION", ""),
        llamacpp_context_length=_env_int("PHANTOM_GRID_LLAMACPP_CONTEXT_LENGTH", 8192),
        llamacpp_gpu_layers=os.getenv("PHANTOM_GRID_LLAMACPP_GPU_LAYERS", "auto"),
        minicpm_gpu_device=os.getenv("PHANTOM_GRID_GPU_DEVICE", "auto"),
        witness_chat_tts=os.getenv("PHANTOM_GRID_WITNESS_CHAT_TTS", "0").strip().lower() not in {"0", "false", "off", "no"},
        witness_voice_dir=_env_path("PHANTOM_GRID_WITNESS_VOICE_DIR", PROJECT_ROOT / "data" / "voices") or PROJECT_ROOT / "data" / "voices",
        max_turns=_env_int("PHANTOM_GRID_MAX_TURNS", 12),
        checks_per_turn=_env_int("PHANTOM_GRID_CHECKS_PER_TURN", 2),
        blocks_per_turn=_env_int("PHANTOM_GRID_BLOCKS_PER_TURN", 1),
        individual_witness_threshold=_env_int("PHANTOM_GRID_INDIVIDUAL_WITNESS_THRESHOLD", 12),
        memory_corruption_per_turn=_env_float("PHANTOM_GRID_MEMORY_CORRUPTION_PER_TURN", 0.08),
    )
