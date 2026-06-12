# Phantom Grid

Local prototype for the revised Commissioner investigation game.

The player is the Commissioner. The hidden culprit moves across a fictional junction graph while the player issues lookout notices, reviews witness responses, blocks movement, and checks junctions. This folder is organized so the current map assets can support the first playable prototype, while later work can add richer landmark parsing through `data/processed/map_atlas.json`.

## Current Layout

```text
app.py
config/
data/
  raw/
    maps/
      images/
      normal_cv_out/
      taxi_cv_out/
      bus_cv_out/
      subway_cv_out/
  processed/
  games/
game/
grid_map/
llm/
scripts/
tools/
```

## Local LLM

The default target is a local llama.cpp OpenAI-compatible server:

```text
http://127.0.0.1:8080/v1/chat/completions
```

Use `scripts/detect_local_llm.py` to find the installed llama.cpp binary and likely local `.gguf` models. Put the chosen paths in `.env` using `.env.example` as the template. The app reads `.env` directly, so no extra dotenv package is needed.

Current local model:

```text
D:\Models\gemma-4-e4b-q8\gemma-4-E4B-it-Q8_0.gguf
```

## Map Layers

The displayed maps intentionally use generated overlay images for now:

- `normal`: `normal_cv_out/junctions_labelled.png`
- `taxi`: `taxi_cv_out/graph_on_map.png`
- `bus`: `bus_cv_out/graph_on_map.png`
- `subway`: `subway_cv_out/graph_on_map.png`

## First Setup

```powershell
python -m pip install -r requirements.txt
python scripts/build_processed_data.py
python scripts/detect_local_llm.py
```

Run the custom `gr.Server` investigation table:

```powershell
python app.py
```

The app serves a custom HTML/CSS/JS frontend at `http://127.0.0.1:7860` and exposes Gradio API endpoints for case actions.

## Immediate Milestone

1. Load map folders and generated graph files.
2. Build `junction_registry.json`, `game_graph.json`, `map_metadata.json`, and placeholder `map_atlas.json`.
3. Show maps and selected junction routes in a custom `gr.Server` frontend.
4. Add game state, checks, blocks, mock witnesses, then LLM calls.
