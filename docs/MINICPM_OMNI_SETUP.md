# MiniCPM-o 4.5 Setup

Phantom Grid expects three external components. Keep these outside the project so model weights and compiled binaries are not copied into source control.

## 1. Download the GGUF snapshot

Install the Hugging Face CLI and preserve the repository's nested module folders:

```powershell
py -m pip install -U huggingface_hub
huggingface-cli download openbmb/MiniCPM-o-4_5-gguf --local-dir D:\Models\MiniCPM-o-4_5-gguf
```

The directory must contain one or more root LLM quantizations and all companion modules:

```text
MiniCPM-o-4_5-gguf/
  MiniCPM-o-4_5-Q4_K_M.gguf
  audio/
  tts/
  token2wav-gguf/
  vision/
```

The Settings model scan lists root quantizations only and reports whether the audio, TTS, and Token2Wav modules are present.

## 2. Build llama.cpp-omni

The official Comni integration currently uses the `feat/web-demo` branch:

```powershell
git clone https://github.com/tc-mb/llama.cpp-omni.git D:\Tools\llama.cpp-omni
Set-Location D:\Tools\llama.cpp-omni
git checkout feat/web-demo
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release --target llama-server -j
```

The Comni branch expects `build\bin\llama-server` (or `build\bin\Release\llama-server.exe` for multi-config Windows builds). The packaged first-run installer uses project-local CMake, Ninja, and Zig for a CPU-capable build without requiring Visual Studio.

## 3. Install the Comni gateway

```powershell
git clone https://github.com/OpenBMB/MiniCPM-o-Demo.git D:\Tools\MiniCPM-o-Demo
Set-Location D:\Tools\MiniCPM-o-Demo
git checkout Comni
py -3.10 -m venv .venv\base
.\.venv\base\Scripts\python.exe -m pip install -U pip
.\.venv\base\Scripts\python.exe -m pip install "torch==2.8.0" "torchaudio==2.8.0"
.\.venv\base\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config.example.json config.json
```

The Phantom Grid launcher updates `config.json` at launch with the selected model, context length, GPU layers, ports, and external paths. It starts one worker and an HTTP gateway at `127.0.0.1:8006` by default.

## 4. Configure Phantom Grid

Open Settings and fill in:

- Comni checkout: `D:\Tools\MiniCPM-o-Demo`
- llama.cpp-omni root: `D:\Tools\llama.cpp-omni`
- MiniCPM model directory: `D:\Models\MiniCPM-o-4_5-gguf`
- Quantization: choose a scanned root GGUF
- Context: `4096` to `32768`
- GPU layers: `auto`, `0`, or a non-negative integer

Press **Start MiniCPM-o**. First model load can take a minute or more. The browser will refuse to create or advance an AI case until the gateway health check succeeds.

## Context adaptation

The selected context is also the game's memory budget. Smaller contexts retain fewer recent story segments and interview turns, while older events are compacted into a continuity synopsis. Larger contexts preserve more recent detail. Story decisions, observable facts, and persisted case history are never discarded.

## Reference voices

Development reference WAVs live in `data/voices`. Each witness receives a stable voice ID and that WAV is supplied to MiniCPM-o for TTS and live interviews. Review `data/voices/README.md` before distributing a build.

## Upstream references

- https://github.com/OpenBMB/MiniCPM-o-Demo/tree/Comni
- https://github.com/tc-mb/llama.cpp-omni/tree/feat/web-demo
- https://huggingface.co/openbmb/MiniCPM-o-4_5-gguf
