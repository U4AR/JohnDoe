# Phantom Grid

Phantom Grid is a local, browser-based investigation game. You play the Commissioner, tracking a hidden culprit across a fictional London transport map by issuing notices, interviewing witnesses, checking junctions, and placing police tactics.

The application runs locally with Python and serves its interface at:

```text
http://127.0.0.1:7860
```

## Requirements

- Windows 10 or 11
- Python 3.10 or newer (Python 3.12 is currently used for development)
- Git, for automatic local AI setup
- Internet access for the first installation and model download
- Several GB of free disk space for the optional MiniCPM-o model and build files

A GPU is optional. The local AI runtime can run on CPU, although responses will be slower.

## Quick Start

From PowerShell in the project directory:

```powershell
.\run_game.ps1
```

You can also double-click `run_game.cmd` in File Explorer.

The launcher will:

1. Create `.venv` if it does not exist.
2. Install the packages in `requirements.txt`.
3. Start the local web server.
4. Open `http://127.0.0.1:7860` in the default browser.

Keep the launcher window open while playing. Press `Ctrl+C`, or close the window, to stop the app.

## First AI Setup

The web interface checks the local AI runtime when it opens. If MiniCPM-o is not installed, choose the model/device options on the setup screen and start the installation.

The managed setup stores downloads and compiled files under `runtime/`. It installs the Comni gateway, `llama.cpp-omni`, build tools, and the `openbmb/MiniCPM-o-4_5-gguf` model. This can take a while on the first run. Progress and errors are displayed in the browser and written to `runtime/provisioner.log`.

GPU layers may be set to:

- `auto`: offload as much as possible to the detected GPU
- `0`: CPU-only mode
- A non-negative number: partially offload that many layers

The app also supports a custom GGUF through a managed `llama-server`, or a user-started OpenAI-compatible llama.cpp server. These options are available in **Settings**.

For a fully manual MiniCPM-o installation, see [docs/MINICPM_OMNI_SETUP.md](docs/MINICPM_OMNI_SETUP.md).

## Manual Installation

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Start the server:

```powershell
python app.py
```

Then open [http://127.0.0.1:7860](http://127.0.0.1:7860).

If PowerShell blocks virtual-environment activation, activation is optional. Run the environment's Python directly:

```powershell
.\.venv\Scripts\python.exe app.py
```

## Configuration

Runtime settings can be changed from the in-app **Settings** panel. Environment variables may also be placed in a project-root `.env` file.

To create a starting configuration:

```powershell
Copy-Item .env.example .env
```

Common settings include:

| Variable | Purpose |
| --- | --- |
| `PHANTOM_GRID_LLM_PROVIDER` | `minicpm_omni`, `llama_cpp_server`, or `external_llama_cpp_server` |
| `PHANTOM_GRID_OMNI_GATEWAY_URL` | MiniCPM-o gateway URL; defaults to `http://127.0.0.1:8006` |
| `PHANTOM_GRID_LLAMACPP_BASE_URL` | OpenAI-compatible llama.cpp API base URL |
| `PHANTOM_GRID_LLAMACPP_CONTEXT_LENGTH` | Model context size; defaults to `8192` |
| `PHANTOM_GRID_LLAMACPP_GPU_LAYERS` | GPU offload setting: `auto`, `0`, or a layer count |
| `PHANTOM_GRID_MAX_TURNS` | Maximum turns in a case |

Do not commit `.env` when it contains machine-specific paths or private configuration.

## Map Data

Processed map data is included in `data/processed/`, so rebuilding it is not normally required. To regenerate and validate it from the raw map sources:

```powershell
.\.venv\Scripts\python.exe scripts\build_processed_data.py
.\.venv\Scripts\python.exe scripts\validate_map_atlas.py
```

The game currently uses these rendered map layers:

- `normal`: `data/raw/maps/normal_cv_out/junctions_labelled.png`
- `taxi`: `data/raw/maps/taxi_cv_out/graph_on_map.png`
- `bus`: `data/raw/maps/bus_cv_out/graph_on_map.png`
- `subway`: `data/raw/maps/subway_cv_out/graph_on_map.png`

## Tests

Run the test suite from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Troubleshooting

**Port 7860 is already in use**

Stop the other Phantom Grid/Python process using the port, then launch again:

```powershell
Get-NetTCPConnection -LocalPort 7860 | Select-Object OwningProcess
Stop-Process -Id <process-id>
```

**The launcher closes or the page does not open**

Check `app_run.err.log` and `app_run.log` in the project root.

**The web page opens but Start Game is disabled**

The AI service is not ready. Check the setup status in the browser, review `runtime/provisioner.log`, or open **Settings** and verify the selected provider, model path, context size, and GPU settings.

**The first model load appears stuck**

Initial downloads, compilation, and model loading can be slow. Check `runtime/provisioner.log` for continuing activity. Downloads are designed to resume when possible.

## Project Layout

```text
app.py                 Local web server and API routes
config/                Environment and application settings
data/                  Maps, voices, processed graph data, and saved games
game/                  Game rules, state, turns, witnesses, and story logic
grid_map/              Map graph loading, validation, and atlas helpers
llm/                   LLM, MiniCPM-o, audio, and structured-output clients
scripts/               Setup, data-building, validation, and smoke-test tools
tests/                 Pytest test suite
ui/web/                HTML, CSS, JavaScript, and static UI assets
run_game.ps1           Main Windows launcher
run_game.cmd           Double-click launcher
```

Saved cases are written to `data/games/` by default.
