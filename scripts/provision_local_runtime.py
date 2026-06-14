from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import time
import zipfile
from pathlib import Path


MODEL_REPO = "openbmb/MiniCPM-o-4_5-gguf"
COMNI_REPO = "https://github.com/OpenBMB/MiniCPM-o-Demo.git"
LLAMA_REPO = "https://github.com/tc-mb/llama.cpp-omni.git"
COMNI_ARCHIVE = "https://github.com/OpenBMB/MiniCPM-o-Demo/archive/refs/heads/Comni.zip"
LLAMA_ARCHIVE = "https://github.com/tc-mb/llama.cpp-omni/archive/refs/heads/feat/web-demo.zip"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument(
        "--model-file",
        default="MiniCPM-o-4_5-Q4_K_M.gguf",
        help="The MiniCPM-o-4_5-{quant}.gguf filename in openbmb/MiniCPM-o-4_5-gguf to download.",
    )
    args = parser.parse_args()
    root = Path(args.runtime_root).resolve()
    model_file = args.model_file.strip() or "MiniCPM-o-4_5-Q4_K_M.gguf"
    root.mkdir(parents=True, exist_ok=True)
    worker_lock = acquire_worker_lock(root / "setup.worker.lock")
    if worker_lock is None:
        return 0
    status_path = root / "setup_status.json"
    log_path = root / "setup.log"
    pid_path = root / "setup.pid"
    pid_path.write_text(str(os.getpid()), encoding="ascii")

    def report(stage: str, message: str, *, progress: int, state: str = "running") -> None:
        payload = {
            "state": state,
            "stage": stage,
            "message": message,
            "progress": progress,
            "updated_at": time.time(),
        }
        try:
            temporary = status_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            _atomic_replace(temporary, status_path)
        except OSError as exc:
            # Status updates are best-effort: a stuck AV/indexer/reader race
            # must not abort an in-progress install. The next report() refreshes.
            _append_log(log_path, f"[status] could not refresh setup_status.json: {exc}\n")
        _append_log(log_path, f"[{stage}] {message}\n")

    try:
        cmake = find_tool("cmake")
        comni = root / "MiniCPM-o-Demo"
        llama = root / "llama.cpp-omni"
        models = root / "models" / "MiniCPM-o-4_5-gguf"

        report("comni", "Downloading the MiniCPM-o gateway...", progress=5)
        download_source(COMNI_ARCHIVE, comni, root / "downloads")
        apply_comni_compatibility(comni)

        report("llama", "Downloading llama.cpp-omni...", progress=15)
        download_source(LLAMA_ARCHIVE, llama, root / "downloads")
        apply_source_compatibility(llama)

        server = find_llama_server(llama)
        if server is None:
            report("llama", "Building the local llama.cpp server...", progress=25)
            build_dir = llama / "build"
            if build_dir.exists():
                shutil.rmtree(build_dir)
            configure = [str(cmake), "-B", "build", "-DCMAKE_BUILD_TYPE=Release", "-DLLAMA_CURL=OFF"]
            if os.name == "nt":
                configure.extend(windows_toolchain(root))
            run(configure, llama, log_path)
            run([str(cmake), "--build", "build", "--config", "Release", "--target", "llama-server", "-j"], llama, log_path)
            server = find_llama_server(llama)
            if server is None:
                raise RuntimeError("llama-server was not produced by the build.")

        python = comni_python(comni)
        if not python.exists():
            report("python", "Creating the private MiniCPM-o Python environment...", progress=45)
            run([sys.executable, "-m", "venv", str(python.parent.parent)], root, log_path)
        marker = comni / ".phantom_grid_dependencies_ready"
        if not marker.exists():
            report("python", "Installing MiniCPM-o runtime dependencies...", progress=52)
            run([str(python), "-m", "pip", "install", "--upgrade", "pip"], comni, log_path)
            run([str(python), "-m", "pip", "install", "torch==2.8.0", "torchaudio==2.8.0"], comni, log_path)
            run([str(python), "-m", "pip", "install", "-r", "requirements.txt"], comni, log_path)
            marker.write_text("ready\n", encoding="ascii")

        report("model", f"Downloading MiniCPM-o model files ({model_file}). This is the large step...", progress=65)
        models.mkdir(parents=True, exist_ok=True)
        download_model_files(models, report, llm_filename=model_file)
        report("complete", "Local AI runtime is installed.", progress=100, state="complete")
        pid_path.unlink(missing_ok=True)
        release_worker_lock(worker_lock)
        return 0
    except Exception as exc:
        report("error", str(exc), progress=0, state="error")
        pid_path.unlink(missing_ok=True)
        release_worker_lock(worker_lock)
        return 1


def download_model_files(destination: Path, report, *, llm_filename: str = "MiniCPM-o-4_5-Q4_K_M.gguf") -> None:
    from huggingface_hub import hf_hub_url, model_info

    info = model_info(MODEL_REPO, files_metadata=True)
    available_llms = {
        sibling.rfilename
        for sibling in info.siblings
        if sibling.rfilename.startswith("MiniCPM-o-4_5-") and sibling.rfilename.endswith(".gguf")
        and not any(
            sibling.rfilename.startswith(prefix)
            for prefix in ("audio/", "vision/", "tts/", "token2wav-gguf/")
        )
    }
    if llm_filename not in available_llms:
        available_list = ", ".join(sorted(available_llms)) or "none"
        raise RuntimeError(
            f"Selected quantization '{llm_filename}' is not published in {MODEL_REPO}. "
            f"Available: {available_list}. Pick another variant in the first-run picker."
        )
    wanted = []
    for sibling in info.siblings:
        name = sibling.rfilename
        if name == llm_filename or (
            name.startswith(("audio/", "vision/", "tts/", "token2wav-gguf/")) and name.endswith(".gguf")
        ):
            wanted.append((name, int(sibling.size or 0)))
    total = sum(size for _, size in wanted)
    completed = sum(
        min((destination / name).stat().st_size, size)
        for name, size in wanted
        if (destination / name).exists()
    )
    for name, size in wanted:
        target = destination / name
        if target.exists() and target.stat().st_size == size:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "Phantom-Grid/1.0"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = urllib.request.Request(hf_hub_url(MODEL_REPO, name), headers=headers)
        with urllib.request.urlopen(request, timeout=60) as response:
            append = offset > 0 and response.status == 206
            if not append:
                offset = 0
            with partial.open("ab" if append else "wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    offset += len(chunk)
                    done = completed + min(offset, size)
                    percent = 65 + int((done / total) * 34) if total else 65
                    report(
                        "model",
                        f"Downloading {name} ({done / 1024**3:.1f} / {total / 1024**3:.1f} GB)...",
                        progress=min(percent, 99),
                    )
        if partial.stat().st_size != size:
            raise RuntimeError(f"Incomplete download for {name}: {partial.stat().st_size} of {size} bytes.")
        _atomic_replace(partial, target)
        completed += size


def acquire_worker_lock(path: Path):
    handle = path.open("a+b")
    handle.seek(0)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except OSError:
        handle.close()
        return None


def release_worker_lock(handle) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def find_tool(name: str) -> Path:
    detected = shutil.which(name)
    if detected:
        return Path(detected)
    executable_name = f"{name}.exe" if os.name == "nt" else name
    bundled = Path(sys.executable).parent / executable_name
    if not bundled.exists():
        raise RuntimeError(f"{name} is required to install the local AI runtime but was not found on PATH.")
    return bundled


def download_source(url: str, destination: Path, downloads: Path) -> None:
    if destination.exists():
        return
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / f"{destination.name}.zip"
    urllib.request.urlretrieve(url, archive)
    extract_root = downloads / f"{destination.name}-extract"
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir()
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extract_root)
    roots = [item for item in extract_root.iterdir() if item.is_dir()]
    if len(roots) != 1:
        raise RuntimeError(f"Unexpected source archive layout for {destination.name}.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(roots[0]), str(destination))
    shutil.rmtree(extract_root)


def run(command: list[str], cwd: Path, log_path: Path) -> None:
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"$ {' '.join(command)}\n")
        completed = subprocess.run(command, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT, check=False)
    if completed.returncode:
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(command)}. See {log_path}.")


def _is_transient_sharing_error(exc: OSError) -> bool:
    # Windows ERROR_ACCESS_DENIED (5), ERROR_SHARING_VIOLATION (32), and
    # ERROR_LOCK_VIOLATION (33) — what AV, the Search indexer, or a concurrent
    # reader produce when they briefly hold a handle on the file. On POSIX
    # winerror is None so this is False; os.replace is atomic there.
    return getattr(exc, "winerror", None) in (5, 32, 33)


def _atomic_replace(source: Path, destination: Path, *, attempts: int = 20) -> None:
    # Survives Windows file-sharing races on rename: real-time AV and the
    # Search indexer routinely open new files in fresh directories for
    # scanning, briefly blocking os.replace. Retries with backoff (~5 s
    # budget). POSIX exits on the first iteration.
    delay = 0.05
    last_error: OSError | None = None
    for _ in range(attempts):
        try:
            os.replace(source, destination)
            return
        except OSError as exc:
            if not _is_transient_sharing_error(exc):
                raise
            last_error = exc
            time.sleep(delay)
            delay = min(delay * 1.6, 0.5)
    assert last_error is not None
    raise last_error


def _append_log(log_path: Path, line: str) -> None:
    try:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        pass


def _msvc_cuda_args() -> list[str] | None:
    # Return cmake configure flags for MSVC + CUDA, or None if either isn't
    # available. We probe for both VS BuildTools/Community (via vswhere) and
    # the NVIDIA CUDA Toolkit, then point cmake's toolset spec at CUDA's MSBuild
    # integration files (which live in extras\visual_studio_integration). This
    # avoids the common "No CUDA toolset found" error when CUDA's .props files
    # weren't auto-copied into the VS BuildTools BuildCustomizations folder.
    if os.name != "nt":
        return None
    vs_install = _find_visual_studio()
    cuda_root = _find_cuda_root()
    if vs_install is None or cuda_root is None:
        return None
    # CMAKE_CUDA_ARCHITECTURES selection: cover the realistic NVIDIA GeForce
    # lineup users are likely on. Drop pre-Turing (sm_61) since CUDA 12+
    # builds are noticeably slower and most current GPUs are 75+.
    architectures = "75;86;89;90"
    cuda_posix = str(cuda_root).replace("\\", "/")
    # /Zc:preprocessor switches MSVC's cl.exe to the standards-conforming
    # preprocessor. CUDA 13.x CCCL headers (cuda/std/__cccl/preprocessor.h)
    # hard-fail compilation under MSVC's traditional preprocessor; passing
    # the conforming one through nvcc via -Xcompiler is the canonical fix.
    return [
        "-G", "Visual Studio 17 2022",
        "-A", "x64",
        "-T", f"host=x64,cuda={cuda_posix}",
        "-DGGML_CUDA=ON",
        f"-DCMAKE_CUDA_ARCHITECTURES={architectures}",
        "-DCMAKE_CUDA_FLAGS=-Xcompiler /Zc:preprocessor",
        "-DCMAKE_CXX_FLAGS=/Zc:preprocessor",
        "-DCMAKE_C_FLAGS=/Zc:preprocessor",
    ]


def _find_visual_studio() -> Path | None:
    program_files_x86 = os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
    vswhere = Path(program_files_x86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.exists():
        return None
    try:
        completed = subprocess.run(
            [str(vswhere), "-latest", "-products", "*", "-requires",
             "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    install_path = completed.stdout.strip().splitlines()
    if not install_path or not install_path[0]:
        return None
    candidate = Path(install_path[0])
    return candidate if candidate.exists() else None


def _find_cuda_root() -> Path | None:
    candidate = os.environ.get("CUDA_PATH")
    if candidate:
        path = Path(candidate)
        if (path / "bin" / "nvcc.exe").exists():
            return path
    program_files = os.environ.get("ProgramFiles") or r"C:\Program Files"
    base = Path(program_files) / "NVIDIA GPU Computing Toolkit" / "CUDA"
    if not base.exists():
        return None
    versions = sorted(
        (entry for entry in base.iterdir() if entry.is_dir() and entry.name.startswith("v")),
        key=lambda entry: entry.name, reverse=True,
    )
    for version in versions:
        if (version / "bin" / "nvcc.exe").exists():
            return version
    return None


def apply_comni_compatibility(root: Path) -> None:
    # MiniCPM-o-Demo hardcodes TTS+T2W on GPU which OOMs on cards with <8 GB
    # VRAM once the main LLM has loaded. Re-route the two knobs through env
    # vars so launch_minicpm_omni.py can pick CPU TTS for small-VRAM machines.
    backend = root / "core" / "processors" / "cpp_backend.py"
    if not backend.exists():
        return
    source = backend.read_text(encoding="utf-8")
    replacements = [
        (
            '            "tts_gpu_layers": 100,\n',
            '            "tts_gpu_layers": int(os.environ.get("MINICPM_TTS_GPU_LAYERS", "100")),\n',
        ),
        (
            '            "token2wav_device": "gpu:0",\n',
            '            "token2wav_device": os.environ.get("MINICPM_TOKEN2WAV_DEVICE", "gpu:0"),\n',
        ),
    ]
    changed = source
    for old, new in replacements:
        if new not in changed:
            changed = changed.replace(old, new)
    if changed != source:
        backend.write_text(changed, encoding="utf-8")


def apply_source_compatibility(root: Path) -> None:
    header = root / "tools" / "omni" / "omni.h"
    if not header.exists():
        return
    text = header.read_text(encoding="utf-8")
    old = "// Windows compatibility: pid_t is not defined on MSVC\n#ifdef _WIN32\n    typedef int pid_t;\n#endif"
    prior = "// pid_t is absent in MSVC, but is supplied by Zig/Clang on Windows.\n#if defined(_WIN32) && defined(_MSC_VER)\n    typedef int pid_t;\n#endif"
    new = "// pid_t is absent in MSVC, but is supplied by Zig/Clang on Windows.\n#if defined(_WIN32) && defined(_MSC_VER)\n    typedef int pid_t;\n#elif defined(_WIN32)\n    #include <sys/types.h>\n#endif"
    updated = text.replace(old, new).replace(prior, new)
    if updated != text:
        header.write_text(updated, encoding="utf-8")

    replacements = {
        # omni.cpp needs STB_IMAGE_IMPLEMENTATION so stbi_load_from_memory has
        # a body when omni.dll links. Earlier versions of this script stripped
        # the define (it doubled with mtmd-helper.cpp under Zig+Clang), but
        # under MSVC each translation unit needs its own copy or the omni
        # target hits LNK2019 on stbi_*.
        root / "tools" / "omni" / "audition.cpp": [
            ("bool preprocess_audio(\n", "bool preprocess_audio_omni(\n"),
            ("whisper_preprocessor::preprocess_audio(\n", "whisper_preprocessor::preprocess_audio_omni(\n"),
        ],
        root / "tools" / "omni" / "audition.h": [
            ("bool preprocess_audio(\n", "bool preprocess_audio_omni(\n"),
        ],
        root / "tools" / "omni" / "omni-impl.h": [("g_logger_state", "omni_g_logger_state")],
        root / "tools" / "omni" / "vision.cpp": [("g_logger_state", "omni_g_logger_state")],
    }
    for path, edits in replacements.items():
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        changed = source
        for old_text, new_text in edits:
            if old_text == "g_logger_state" and "omni_g_logger_state" in changed:
                continue
            changed = changed.replace(old_text, new_text)
        if changed != source:
            path.write_text(changed, encoding="utf-8")

    audition = root / "tools" / "omni" / "audition.cpp"
    if audition.exists():
        source = audition.read_text(encoding="utf-8")
        if "#define MINIAUDIO_IMPLEMENTATION" not in source:
            source = source.replace("#ifndef OMNI_AUDIO_DEBUG", "#define MINIAUDIO_IMPLEMENTATION\n#ifndef OMNI_AUDIO_DEBUG", 1)
        if "#define ma_atomic_global_lock omni_ma_atomic_global_lock" not in source:
            source = source.replace(
                "#define MINIAUDIO_IMPLEMENTATION",
                "#define ma_atomic_global_lock omni_ma_atomic_global_lock\n#define MINIAUDIO_IMPLEMENTATION",
                1,
            )
        audition.write_text(source, encoding="utf-8")


def find_llama_server(root: Path) -> Path | None:
    candidates = (
        root / "build" / "bin" / "Release" / "llama-omni-server.exe",
        root / "build" / "bin" / "llama-omni-server.exe",
        root / "build" / "bin" / "llama-omni-server",
        root / "build" / "bin" / "Release" / "llama-server.exe",
        root / "build" / "bin" / "llama-server.exe",
        root / "build" / "bin" / "llama-server",
    )
    return next((path for path in candidates if path.exists()), None)


def windows_toolchain(root: Path) -> list[str]:
    # Prefer MSVC + CUDA when both are present — that's the only path to a
    # GPU-accelerated llama-server on Windows. Zig+Clang is a CPU-only fallback
    # for machines without VS BuildTools / NVIDIA CUDA installed.
    cuda_args = _msvc_cuda_args()
    if cuda_args is not None:
        return cuda_args
    import ziglang

    zig = Path(ziglang.__file__).parent / "zig.exe"
    ninja = find_tool("ninja")
    wrappers = root / "toolchain"
    wrappers.mkdir(parents=True, exist_ok=True)
    cc = wrappers / "zig-cc.cmd"
    cxx = wrappers / "zig-cxx.cmd"
    ar = wrappers / "zig-ar.cmd"
    ranlib = wrappers / "zig-ranlib.cmd"
    cc.write_text(f'@"{zig}" cc %*\n', encoding="ascii")
    cxx.write_text(f'@"{zig}" c++ %*\n', encoding="ascii")
    ar.write_text(f'@"{zig}" ar %*\n', encoding="ascii")
    ranlib.write_text(f'@"{zig}" ranlib %*\n', encoding="ascii")
    return [
        "-G", "Ninja",
        f"-DCMAKE_MAKE_PROGRAM={ninja}",
        f"-DCMAKE_C_COMPILER={cc}",
        f"-DCMAKE_CXX_COMPILER={cxx}",
        f"-DCMAKE_AR={ar}",
        f"-DCMAKE_RANLIB={ranlib}",
    ]


def comni_python(root: Path) -> Path:
    if os.name == "nt":
        return root / ".venv" / "base" / "Scripts" / "python.exe"
    return root / ".venv" / "base" / "bin" / "python"


if __name__ == "__main__":
    raise SystemExit(main())
