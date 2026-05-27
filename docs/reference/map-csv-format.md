# Map CSV Format

Format reference for the map CSVs stored under `maps/`. These files describe a single in-game map as a set of nodes positioned on the minimap; the agent reads them at runtime to build a pathfinding graph, and the in-app Map Editor reads/writes them as well.

The format is **mostly CSV** but has several non-standard conventions documented below — leading `#` comment lines, a tuple field stored as a quoted string, all-caps booleans, and row-order semantics. If you edit one of these files by hand, use **Notepad** (or any plain editor); PyCharm hides leading comment lines, which makes the metadata line easy to miss.

## File structure

A map CSV has three regions in this order:

```
# minimap_size=W,H                                      <-- (1) optional metadata
nodetype,pos_in_minimap,can_fall,...                    <-- (2) header (required)
blue_node,"(56, 34)",FALSE,FALSE,FALSE,FALSE            <-- (3) data rows (1+)
blue_node,"(112, 47)",FALSE,FALSE,FALSE,FALSE
```

1. **Metadata lines** — zero or more lines starting with `#`. Currently only `minimap_size` is recognized. Other `#` lines (plain comments or future keys) are silently ignored.
2. **Header row** — required, must match the exact column order in `CSV_HEADER` (see `src/controller/map_csv.py:23`).
3. **Data rows** — one node per row. At least one row is needed for the agent to do anything useful, though the file is valid with zero data rows.

## Metadata lines (the `#`-prefix region)

Format: `# key=value` (whitespace around `#`, `key`, and `value` is tolerated).

### Recognized keys

| Key | Value format | Meaning |
|---|---|---|
| `minimap_size` | `W,H` — two positive integers separated by a comma | Width × height of the minimap the file was authored against, in pixels. |

### `minimap_size` semantics

When present, `minimap_size` is the **authoritative gate** when the editor loads the file: if the saved `W,H` doesn't match the editor's current minimap dimensions, the load is **blocked** with a precise error, even if the nodes would fit within the current minimap. This prevents loading nodes whose absolute pixel coordinates would land in the wrong place on a different-sized minimap.

If the metadata line is malformed (non-integer, wrong number of components, or non-positive integers), the load is blocked with an error. If the metadata line is absent entirely (a legacy CSV), the editor falls back to a per-node bounds check.

The runtime parser (`csv_parser.CSVParser`) ignores `#` lines unconditionally — it does not perform the dimension check.

### Unknown keys & plain comments

`#` lines whose key is not in the recognized list above, and `#` lines without an `=` at all (plain comments), are silently ignored. This keeps the format forward-compatible: a future writer can add `# editor_version=2` without breaking existing readers.

If `minimap_size` appears multiple times, the **first occurrence wins**.

## Header row

The header MUST be these six columns in this exact order:

```
nodetype,pos_in_minimap,can_fall,fall_dist_exceeds_vertical_tp,is_left_platform_edge,is_right_platform_edge
```

Source of truth: `CSV_HEADER` in `src/controller/map_csv.py:23`. Both readers compare against this list and reject the file on any mismatch.

## Per-column value formats

| Column | Type | Format | Notes |
|---|---|---|---|
| `nodetype` | string | `blue_node` \| `orange_node` | Case-sensitive. See "Node types" below. |
| `pos_in_minimap` | tuple stored as quoted string | `"(x, y)"` — two ints, top-left origin | Parsed via `ast.literal_eval`. The quotes are required because the comma inside `(x, y)` would otherwise be a CSV field separator. Canonical written form has one space after the comma: `(56, 34)`. |
| `can_fall` | bool | `TRUE` \| `FALSE` | **All-caps.** Lowercase `true`/`false` is rejected. |
| `fall_dist_exceeds_vertical_tp` | bool | `TRUE` \| `FALSE` | All-caps. |
| `is_left_platform_edge` | bool | `TRUE` \| `FALSE` | All-caps. |
| `is_right_platform_edge` | bool | `TRUE` \| `FALSE` | All-caps. |

Boolean field semantics are documented in `src/controller/node.py:10` (the `Node.__init__` docstring) and applied in `src/controller/path_graph.py` (edge-validity rules). They control pathfinding behavior: whether the agent may drop from this node, whether falling would exceed a vertical-teleport ability, and which side of a platform the node sits on.

## Node types

- **`blue_node`** — a node that the agent visits as part of its rotation. Blue nodes are added to `map_rotation_order` in file order (see "Row order" below).
- **`orange_node`** — a node that exists in the graph but is **not** part of the rotation cycle (intermediate / junction node).

Both are accepted by both readers (`VALID_NODETYPES` in `src/controller/map_csv.py:32`).

## Row order is semantic

Row order is **not** cosmetic. The first reader pass populates two structures:

- `node_map: dict[uuid → Node]` — every row, regardless of type.
- `map_rotation_order: list[Node]` — only `blue_node` rows, in **file order**.

The runtime agent cycles through `map_rotation_order` in order, so editing the file to reorder blue-node rows directly changes the agent's visit sequence.

The Map Editor preserves rotation order on save: it writes blue nodes first (in `rotation_order` order), then orange nodes sorted by ascending local-id. See `write_editor_nodes` in `src/controller/map_csv.py:139`.

## Two readers

There are **two independent code paths** that read this format. They share the header constant (`CSV_HEADER`) but diverge in what they return and how strict they are.

| Reader | Returns | Used by | Notes |
|---|---|---|---|
| `src.controller.csv_parser.CSVParser.parseCSV` | Populates `map_rotation_order` + `node_map` with real `Node` instances (bumps `Node.node_id_counter`). | Runtime agent at `loadMap()` time. | Ignores `#` lines. Does NOT enforce or read `minimap_size` — bounds checks happen elsewhere if at all. |
| `src.controller.map_csv.read_editor_nodes` | `Result[(List[EditorNode], List[int], Dict[str, Any]), str]`. | In-app Map Editor (load / save round-trip). | Strict on metadata (malformed `minimap_size` → `Failure`). Uses `EditorNode` (an `@dataclass`), not `Node` — so editor loads do **not** bump `Node.node_id_counter`. |

Why two readers: the editor needs to read CSVs without polluting the agent's runtime state (specifically, without incrementing the global `Node` ID counter or mutating any `MapleAgent` fields). Keeping the I/O separate is an accepted tradeoff — see `docs/superpowers/specs/2026-05-13-map-editor-design.md` §6.

Both readers filter out `#`-prefixed lines before handing the stream to `csv.DictReader`. The filter is what makes the metadata line backwards-compatible with the runtime parser — without it, the extra row would be counted as an extra header column and the file would be rejected.

## Examples

### Minimal (no metadata, one node)

```csv
nodetype,pos_in_minimap,can_fall,fall_dist_exceeds_vertical_tp,is_left_platform_edge,is_right_platform_edge
blue_node,"(56, 34)",FALSE,FALSE,FALSE,FALSE
```

Loads cleanly under both readers. The editor will accept this and treat it as a legacy CSV (no dimension gate).

### With metadata (editor-written)

```csv
# minimap_size=186,74
nodetype,pos_in_minimap,can_fall,fall_dist_exceeds_vertical_tp,is_left_platform_edge,is_right_platform_edge
blue_node,"(56, 34)",FALSE,FALSE,FALSE,FALSE
blue_node,"(112, 47)",FALSE,FALSE,FALSE,FALSE
blue_node,"(131, 15)",FALSE,FALSE,FALSE,FALSE
```

Editor will reject this on load if the current minimap isn't 186×74. Runtime parser ignores the metadata line and loads regardless.

### Mixed node types with platform-edge flags

```csv
# minimap_size=186,74
nodetype,pos_in_minimap,can_fall,fall_dist_exceeds_vertical_tp,is_left_platform_edge,is_right_platform_edge
blue_node,"(56, 34)",TRUE,FALSE,TRUE,FALSE
blue_node,"(112, 47)",TRUE,FALSE,FALSE,TRUE
orange_node,"(85, 40)",FALSE,FALSE,FALSE,FALSE
```

Rotation order is `(56,34) → (112,47)` (blue nodes in file order). The orange node is part of the graph but not the cycle.

## Gotchas

- **Line endings:** the writer uses `\r\n` for the metadata line to match `csv.writer`'s excel dialect. Reading is tolerant (`open(..., newline="")` + `readlines()`), but if you regenerate files with a different writer, keep the body and metadata line endings consistent.
- **The metadata comma trap:** the metadata line is written with raw `f.write(...)`, not `csv.writer.writerow(...)`. If you ever convert to the latter, the `W,H` value will trigger CSV quoting and break the `#`-prefix filter on read. See the comment in `write_editor_nodes` at `src/controller/map_csv.py:159`.
- **Hidden in PyCharm:** PyCharm's CSV viewer hides leading comment lines by default. When verifying metadata, open in Notepad (or `Get-Content` in PowerShell) instead.
- **`pos_in_minimap` must be a 2-tuple of ints, not floats.** `(56.0, 34.0)` parses but is rejected by both readers' validation.
- **All-caps booleans only.** This is a quirk of the format, not a Python convention. Lowercase `true`/`false` fails validation in both readers.
