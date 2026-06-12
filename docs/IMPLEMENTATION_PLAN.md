# Implementation Plan

## Now

- Keep the current fictional map assets under `data/raw/maps`.
- Generate `data/processed/junction_registry.json` from the normal map graph.
- Generate `data/processed/game_graph.json` by merging taxi, bus, and subway layer edges.
- Keep `data/processed/map_atlas.json` as an editable landmark/district registry. It starts empty and can later be filled manually or by a builder.
- Use a local llama.cpp server for all LLM calls. The binary and model paths live in settings.
- For witness memory corruption, keep the behavior prompt-based: the prompt asks the LLM to slightly corrupt the current witness info without fully rewriting it.

## Next Playable Slice

1. Gradio map viewer with layer switching.
2. Click or type a junction ID and show legal transport moves.
3. New game creation with hidden culprit state.
4. Junction check win condition.
5. Route and mode block validation.
6. Mock lookout and witness batches.
7. Witness threshold gating.
8. Witness-question prompt through local llama.cpp.
9. Culprit-move prompt through local llama.cpp.
10. Turn-end witness memory corruption prompt.

