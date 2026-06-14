from __future__ import annotations

import json
import platform
import shutil
import subprocess
from dataclasses import dataclass


# Candidate quantizations OpenBMB ships for MiniCPM-o-4_5. The provisioner
# downloads exactly one of these. Q4_K_M is the safe default — small, fast,
# and what the HF repo guarantees. Other entries are best-effort: if OpenBMB
# hasn't published that variant the provisioner raises a clear error.
QUANTIZATION_CATALOG: list[dict] = [
    {
        "id": "MiniCPM-o-4_5-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "label": "Q4_K_M (recommended) — ~4 GB, 4-bit, fast",
        "size_gb": 4.0,
        "tier": "recommended",
    },
    {
        "id": "MiniCPM-o-4_5-Q5_K_M.gguf",
        "quant": "Q5_K_M",
        "label": "Q5_K_M — ~5 GB, 5-bit, balanced",
        "size_gb": 5.0,
        "tier": "balanced",
    },
    {
        "id": "MiniCPM-o-4_5-Q6_K.gguf",
        "quant": "Q6_K",
        "label": "Q6_K — ~5.5 GB, 6-bit, higher fidelity",
        "size_gb": 5.5,
        "tier": "balanced",
    },
    {
        "id": "MiniCPM-o-4_5-Q8_0.gguf",
        "quant": "Q8_0",
        "label": "Q8_0 — ~7 GB, 8-bit, near-lossless",
        "size_gb": 7.0,
        "tier": "quality",
    },
    {
        "id": "MiniCPM-o-4_5-F16.gguf",
        "quant": "F16",
        "label": "F16 — ~14 GB, full precision, best quality",
        "size_gb": 14.0,
        "tier": "quality",
    },
]


# Reasonable defaults for the GPU layers selector. "auto" lets llama.cpp pick;
# 0 forces CPU-only; explicit counts offload the first N transformer layers.
GPU_LAYER_PRESETS: list[dict] = [
    {"id": "auto", "label": "Auto (let llama.cpp choose)"},
    {"id": "99", "label": "All layers on GPU (fastest if VRAM allows)"},
    {"id": "32", "label": "32 layers on GPU (~mid VRAM)"},
    {"id": "16", "label": "16 layers on GPU (lower VRAM)"},
    {"id": "0", "label": "0 layers on GPU (CPU only)"},
]


CONTEXT_LENGTH_PRESETS: list[dict] = [
    {"id": 4096, "label": "4,096 tokens — lightest"},
    {"id": 8192, "label": "8,192 tokens — recommended"},
    {"id": 16384, "label": "16,384 tokens — longer cases"},
    {"id": 24576, "label": "24,576 tokens"},
    {"id": 32768, "label": "32,768 tokens — maximum"},
]


@dataclass(frozen=True)
class RuntimeDevice:
    id: str
    label: str
    vendor: str  # "auto" | "cpu" | "nvidia" | "amd" | "apple"
    index: int | None = None
    vram_mb: int | None = None


def detect_devices() -> list[dict]:
    """Probe the system for runtime devices the model can target.

    Always returns at least the meta options ('auto', 'cpu'). GPU detection
    is best-effort: a missing vendor toolchain (nvidia-smi, rocm-smi) means
    that vendor is omitted, not an error. Probes use a short timeout so a
    hung tool can't block the first-run picker.
    """
    devices: list[RuntimeDevice] = [
        RuntimeDevice(id="auto", label="Auto-detect best device", vendor="auto"),
        RuntimeDevice(id="cpu", label="CPU only (slow, no GPU acceleration)", vendor="cpu"),
    ]
    devices.extend(_probe_nvidia())
    devices.extend(_probe_amd())
    devices.extend(_probe_apple())
    return [_serialise(d) for d in devices]


def quantization_catalog() -> list[dict]:
    return [dict(item) for item in QUANTIZATION_CATALOG]


def gpu_layer_presets() -> list[dict]:
    return [dict(item) for item in GPU_LAYER_PRESETS]


def context_length_presets() -> list[dict]:
    return [dict(item) for item in CONTEXT_LENGTH_PRESETS]


def _serialise(device: RuntimeDevice) -> dict:
    payload: dict = {"id": device.id, "label": device.label, "vendor": device.vendor}
    if device.index is not None:
        payload["index"] = device.index
    if device.vram_mb is not None:
        payload["vram_mb"] = device.vram_mb
    return payload


def _probe_nvidia() -> list[RuntimeDevice]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return []
    try:
        completed = subprocess.run(
            [nvidia_smi, "--query-gpu=index,name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    devices: list[RuntimeDevice] = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            index = int(parts[0])
            name = parts[1].strip()
            vram_mb = int(float(parts[2]))
        except ValueError:
            continue
        if name.lower().startswith("nvidia "):
            name = name[len("nvidia "):]
        vram_gb = vram_mb / 1024 if vram_mb else 0
        devices.append(RuntimeDevice(
            id=f"cuda:{index}",
            label=f"NVIDIA {name} ({vram_gb:.1f} GB)" if vram_gb else f"NVIDIA {name}",
            vendor="nvidia",
            index=index,
            vram_mb=vram_mb or None,
        ))
    return devices


def _probe_amd() -> list[RuntimeDevice]:
    rocm_smi = shutil.which("rocm-smi")
    if not rocm_smi:
        return []
    try:
        completed = subprocess.run(
            [rocm_smi, "--showproductname", "--showmeminfo", "vram", "--json"],
            capture_output=True, text=True, timeout=4, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    try:
        data = json.loads(completed.stdout or "{}")
    except (ValueError, json.JSONDecodeError):
        return []
    devices: list[RuntimeDevice] = []
    for key, entry in (data or {}).items():
        if not isinstance(entry, dict) or not key.lower().startswith("card"):
            continue
        digits = "".join(ch for ch in key if ch.isdigit())
        if not digits:
            continue
        index = int(digits)
        name = str(entry.get("Card series") or entry.get("Card model") or "AMD GPU").strip() or "AMD GPU"
        vram_bytes = str(entry.get("VRAM Total Memory (B)") or "0")
        try:
            vram_mb = int(int(vram_bytes) / 1024 / 1024)
        except ValueError:
            vram_mb = 0
        vram_label = f" ({vram_mb / 1024:.1f} GB)" if vram_mb else ""
        devices.append(RuntimeDevice(
            id=f"rocm:{index}",
            label=f"AMD {name}{vram_label}",
            vendor="amd",
            index=index,
            vram_mb=vram_mb or None,
        ))
    return devices


def _probe_apple() -> list[RuntimeDevice]:
    if platform.system() != "Darwin" or platform.machine() not in {"arm64", "aarch64"}:
        return []
    return [RuntimeDevice(id="metal", label="Apple Silicon Metal (unified memory)", vendor="apple")]


def resolve_device_env(device_id: str, gpu_layers: str) -> dict[str, str]:
    """Translate the picker's device choice into env-var overrides for the launcher.

    Returns a dict of variables to merge into the launcher subprocess env. The
    important ones:
      - "auto"   -> no overrides (llama.cpp picks).
      - "cpu"    -> force CPU by blanking CUDA/HIP/ROCR visibility AND zero layers.
      - "cuda:N" -> pin to NVIDIA index N via CUDA_VISIBLE_DEVICES.
      - "rocm:N" -> pin to AMD index N via HIP_VISIBLE_DEVICES + ROCR_VISIBLE_DEVICES.
      - "metal"  -> no overrides (Metal is default on Apple Silicon).
    """
    device = (device_id or "auto").strip().lower()
    if device == "cpu" or str(gpu_layers).strip() == "0":
        return {
            "CUDA_VISIBLE_DEVICES": "",
            "HIP_VISIBLE_DEVICES": "",
            "ROCR_VISIBLE_DEVICES": "",
        }
    if device.startswith("cuda:"):
        return {"CUDA_VISIBLE_DEVICES": device.split(":", 1)[1]}
    if device.startswith("rocm:"):
        index = device.split(":", 1)[1]
        return {"HIP_VISIBLE_DEVICES": index, "ROCR_VISIBLE_DEVICES": index}
    return {}
