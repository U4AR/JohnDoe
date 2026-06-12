# Phantom Grid Follow-Up TODO

## Witness Interaction
- Keep witness details in the same map surface: selecting any witness should expand an in-map card, not open a separate window or detached modal.
- Improve witness popups so the expanded card feels primary, larger, and easier to read on the map.
- Keep the secondary witness drawer optional or remove it if the map card covers the full conversation flow.
- Add richer witness conversation controls after the first Ask action, including a few quick question buttons.

## Junction And Blockade UI
- Redesign the junction-click popup so blockade controls appear larger, closer to the user's focus, and visually stronger than the current tray.
- Show transport-specific blockade choices directly from the selected junction or edge.
- Fix discrepancies between drawn junction positions and actual graph junction coordinates.
- Add a calibration/debug overlay for comparing rendered junction pins against the source map artwork.

## Map Layers
- Combine bus, subway, and taxi maps into a single readable transport map mode.
- Keep layer toggles only if they provide useful tactical contrast after the combined transport map exists.
- Verify all active junction, transport, and witness pins align correctly on the combined map.

## Layout
- Invalidate the need for scrolling on normal desktop screens.
- Rework the desktop layout so the complete map, top strip, lookout board, and contextual controls fit in one viewport.
- Keep scrolling only as a fallback for small laptop and mobile screens.
- Re-test common viewport sizes after every major UI layout change.

## Art And Audio
- Replace every prompted placeholder graphic with real local assets.
- Generate or source final assets for the case table background, suspect placeholder, witness portraits, and lookout board texture.
- Keep the existing prompt list until each asset is replaced and checked into the repo.
- Introduce text-to-speech for witness answers and essential case events.
- Add a visible mute/speech toggle separate from sound effects.
- Replace synthetic Web Audio sound effects with final audio files when available.

## Verification
- Add browser-level UI checks for witness pin expansion, Ask button behavior, junction popup behavior, and no-scroll desktop layout.
- Add a visual regression check for junction alignment on each map layer.
- Keep API tests for random starts, witness snapshots, and multi-junction selection.
