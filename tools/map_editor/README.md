# Map Editor Documentation

This folder contains an interactive correction UI for the Scotland Yard map graph outputs.

The editor lets you correct shared junction positions across all maps, draw per-transport routes, save graph files, and generate preview images where each transport graph is plotted over the normal `Map.png` image.

## Start The Editor

Run this from the `maps` folder:

```powershell
python map_editor.py
```

Then open:

```text
http://127.0.0.1:8765/
```

To auto-open the browser:

```powershell
python map_editor.py --open
```

## Files Used

Input map images:

- `Map.png`
- `Taxi.png`
- `Bus.png`
- `Subway.png`

Graph folders:

- `map_cv_out`
- `taxi_cv_out`
- `bus_cv_out`
- `subway_cv_out`

Each graph folder is expected to contain:

- `junctions.csv`
- `graph.json`
- `graph.graphml`
- `junctions_labelled.png`

## Editor Layout

The screen has two main views:

- Left pane: editable map view for the currently selected map.
- Right pane: live preview of the current graph plotted on the base `Map.png`.

Use the map buttons to switch between:

- Full Map
- Taxi
- Bus
- Subway

Changes are shown live when switching maps.

## Editing Junctions

All junctions are shared across all four maps.

If you add, move, or delete a junction on one map, the same junction is updated for every map at the same coordinate and with the same number.

Available tools:

- `Move / select junction`: drag a junction to a nearby corrected position.
- `Add junction`: click anywhere on the map to add a new shared junction.
- `Draw route between 2 junctions`: click one junction, then click another junction to create a route on the current map only.
- `Delete junction or route`: click a route to remove it from the current map, or click a junction to delete it from all maps.

## Renumbering

Junctions are renumbered automatically after add, move, or delete operations.

The renumbering order is top-to-bottom, then left-to-right. Route edges are remapped internally so connections follow the same physical junctions after renumbering.

## Saving Graphs

Click:

```text
Save all graph files
```

This rewrites graph outputs in all four graph folders:

- `junctions.csv`
- `graph.json`
- `graph.graphml`
- `junctions_labelled.png`

The route edges remain separate per map:

- Taxi routes save to `taxi_cv_out`
- Bus routes save to `bus_cv_out`
- Subway routes save to `subway_cv_out`
- Full map routes save to `map_cv_out`

## Saving Preview Images

Click:

```text
Save preview images
```

This creates or updates:

- `taxi_cv_out/graph_on_map.png`
- `bus_cv_out/graph_on_map.png`
- `subway_cv_out/graph_on_map.png`

Each preview image:

- Uses `Map.png` as the background.
- Draws the corresponding transport graph in that transport color.
- Shows numbered junctions.
- Prints the route map name at the top, such as `Bus Routes`.

## Backups

Before saving graph files or preview images, the editor creates a timestamped backup in:

```text
editor_backups/
```

The backups include existing graph files and preview images when present.

## Current Server Port

Default host and port:

```text
http://127.0.0.1:8765/
```

To use a different port:

```powershell
python map_editor.py --port 9000
```

Then open:

```text
http://127.0.0.1:9000/
```

## Troubleshooting

If the page does not load, restart the server:

```powershell
python map_editor.py
```

If port `8765` is already in use, either stop the old server or start on another port:

```powershell
python map_editor.py --port 9000
```

If graph edits do not appear in output files, make sure you clicked `Save all graph files`. Until then, edits are only in the browser.

If preview images do not update, make sure you clicked `Save preview images`.
