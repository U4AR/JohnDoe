from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path


def main() -> int:
    root = Path(os.environ.get("MINICPM_COMNI_ROOT", "")).expanduser().resolve()
    if not root.exists() or not (root / "worker.py").exists() or not (root / "gateway.py").exists():
        print("MINICPM_COMNI_ROOT must point to an OpenBMB/MiniCPM-o-Demo Comni checkout.", file=sys.stderr)
        return 2

    model_dir = Path(os.environ.get("MINICPM_MODEL_DIR", "")).expanduser().resolve()
    llm_model = os.environ.get("MINICPM_LLM_MODEL", "").strip()
    llama_root = Path(os.environ.get("MINICPM_LLAMACPP_ROOT", "")).expanduser().resolve()
    context = int(os.environ.get("MINICPM_CTX_SIZE", "8192"))
    gpu_layers_raw = os.environ.get("MINICPM_N_GPU_LAYERS", "auto").strip().lower()
    gpu_layers = 99 if gpu_layers_raw == "auto" else int(gpu_layers_raw)
    gateway_url = os.environ.get("MINICPM_GATEWAY_URL", "http://127.0.0.1:8006")
    gateway_port = urllib.parse.urlparse(gateway_url).port or 8006
    worker_port = gateway_port + 1

    if not (model_dir / llm_model).exists():
        print(f"Selected model does not exist: {model_dir / llm_model}", file=sys.stderr)
        return 2
    if not llama_root.exists():
        print(f"llama.cpp-omni root does not exist: {llama_root}", file=sys.stderr)
        return 2

    config_path = root / "config.json"
    example_config_path = root / "config.example.json"
    seed_config_path = config_path if config_path.exists() else example_config_path
    config = json.loads(seed_config_path.read_text(encoding="utf-8")) if seed_config_path.exists() else {}
    config["backend"] = "cpp"
    config.setdefault("model", {})["model_path"] = str(model_dir)
    config.setdefault("service", {}).update({
        "gateway_port": gateway_port,
        "worker_base_port": worker_port,
        "num_workers": 1,
    })
    config.setdefault("cpp_backend", {}).update({
        "llamacpp_root": str(llama_root),
        "model_dir": str(model_dir),
        "llm_model": llm_model,
        "ctx_size": context,
        "n_gpu_layers": gpu_layers,
    })
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    python = _external_python(root)
    log_dir = root / "tmp"
    log_dir.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    gpu_device = os.environ.get("MINICPM_GPU_DEVICE", "auto").strip().lower()

    # MiniCPM-o-Demo's cpp_backend defaults to tts_gpu_layers=100 and
    # token2wav_device=gpu:0. On a 6 GB card the main LLM already fills VRAM,
    # so loading TTS on GPU OOMs and crashes llama-server during omni_init.
    # If the user hasn't picked an explicit policy, probe the GPU and keep
    # TTS+T2W on CPU whenever the device has less than ~8 GB free — the
    # text-generation hot path still runs on GPU, which is what matters.
    if "MINICPM_TTS_GPU_LAYERS" not in env or "MINICPM_TOKEN2WAV_DEVICE" not in env:
        keep_tts_on_cpu = _tts_should_use_cpu(gpu_device, gpu_layers)
        env.setdefault("MINICPM_TTS_GPU_LAYERS", "0" if keep_tts_on_cpu else "100")
        env.setdefault("MINICPM_TOKEN2WAV_DEVICE", "cpu" if keep_tts_on_cpu else "gpu:0")
    # Honor the picker's device choice. CPU and zero-layer modes blank every
    # visibility var so llama.cpp falls back to host execution regardless of
    # which backend was compiled in. cuda:N / rocm:N pin the chosen index.
    if gpu_device == "cpu" or gpu_layers == 0:
        env["CUDA_VISIBLE_DEVICES"] = ""
        env["HIP_VISIBLE_DEVICES"] = ""
        env["ROCR_VISIBLE_DEVICES"] = ""
    elif gpu_device.startswith("cuda:"):
        env["CUDA_VISIBLE_DEVICES"] = gpu_device.split(":", 1)[1]
    elif gpu_device.startswith("rocm:"):
        index = gpu_device.split(":", 1)[1]
        env["HIP_VISIBLE_DEVICES"] = index
        env["ROCR_VISIBLE_DEVICES"] = index

    worker_log = (log_dir / "phantom_grid_worker.log").open("a", encoding="utf-8")
    gateway_log = (log_dir / "phantom_grid_gateway.log").open("a", encoding="utf-8")
    worker = subprocess.Popen(
        [str(python), "worker.py", "--port", str(worker_port), "--gpu-id", "0", "--worker-index", "0"],
        cwd=root, env=env, stdout=worker_log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    gateway = subprocess.Popen(
        [str(python), "gateway.py", "--port", str(gateway_port), "--workers", f"127.0.0.1:{worker_port}", "--http"],
        cwd=root, env=env, stdout=gateway_log, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    children = [gateway, worker]

    def stop_children(*_: object) -> None:
        for child in children:
            if child.poll() is None:
                child.terminate()
        deadline = time.time() + 8
        for child in children:
            try:
                child.wait(timeout=max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                child.kill()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, stop_children)
    signal.signal(signal.SIGTERM, stop_children)
    print(f"MiniCPM-o worker PID {worker.pid}; gateway PID {gateway.pid}", flush=True)
    while all(child.poll() is None for child in children):
        time.sleep(1)
    stop_children()
    return 1


def _tts_should_use_cpu(gpu_device: str, gpu_layers: int) -> bool:
    # CPU is the right place for TTS when there's no GPU offload at all.
    if gpu_device == "cpu" or gpu_layers == 0:
        return True
    # Probe NVIDIA total VRAM. <8 GB → main LLM fills it; TTS must run on CPU.
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return False
    try:
        completed = subprocess.run(
            [nvidia_smi, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if completed.returncode != 0:
        return False
    try:
        total_mib = max(int(line.strip()) for line in completed.stdout.splitlines() if line.strip())
    except ValueError:
        return False
    return total_mib < 8192


def _external_python(root: Path) -> Path:
    configured = os.environ.get("MINICPM_COMNI_PYTHON")
    candidates = [
        Path(configured) if configured else None,
        root / ".venv" / "base" / "Scripts" / "python.exe",
        root / ".venv" / "base" / "bin" / "python",
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return Path(sys.executable)


if __name__ == "__main__":
    raise SystemExit(main())
