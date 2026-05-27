# Helix — Program Reference Docs

Reference documentation for non-obvious **file formats and runtime contracts** in this codebase. These docs describe stable surfaces that downstream code depends on; if a field, header, or convention changes, the corresponding doc here changes with it.

This folder is distinct from `docs/superpowers/` (specs, plans, session logs — process artifacts) and is intended to be tracked in git.

## Index

| Doc | What it covers |
|---|---|
| [map-csv-format.md](map-csv-format.md) | Map CSV file layout — metadata line, header columns, per-column value formats, row-order semantics, and the two reader paths (`csv_parser.CSVParser` vs `map_csv.read_editor_nodes`). |

## Not yet documented

These are reference surfaces that may warrant their own doc if they grow non-obvious:

- **`assets/brds/`** — minimap corner-border templates. Naming convention: `{corner}_grayscale.png` + `{corner}_mask.png` where `corner ∈ {left_top, right_top, left_bot, right_bot}`. Consumed by `vision/vision.py::capture_and_process_minimap`.
- **`assets/chr/`** — character icon template (`chr.png`) + alpha mask (`chr_mask.png`). Consumed by `controller/controller.py::MapleAgent.getCharacterCoords`.
- **`SharedInfo`** — cross-thread state contract between vision worker and controller (`minimap_frame` + `minimap_frame_lock`).

Add a file here when the surface stabilizes enough that drifting docs would be worse than no docs.
