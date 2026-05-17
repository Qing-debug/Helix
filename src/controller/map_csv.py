"""
Pure CSV I/O for the in-GUI map editor.

Deliberately independent of src.controller.csv_parser (CSVParser) and
src.controller.node (Node) so that:
  1. Editor loads don't bump Node.node_id_counter.
  2. Editor I/O lifecycle stays isolated from the agent's runtime state.

Shares the CSV header format with CSVParser. The duplication is an accepted
tradeoff per docs/superpowers/specs/2026-05-13-map-editor-design.md section 6.
"""

import ast
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, List, Dict

from returns.result import Result, Success, Failure


CSV_HEADER = [
    "nodetype",
    "pos_in_minimap",
    "can_fall",
    "fall_dist_exceeds_vertical_tp",
    "is_left_platform_edge",
    "is_right_platform_edge",
]

VALID_NODETYPES = {"blue_node", "orange_node"}
BOOL_FIELDS = (
    "can_fall",
    "fall_dist_exceeds_vertical_tp",
    "is_left_platform_edge",
    "is_right_platform_edge",
)


@dataclass
class EditorNode:
    local_id: int                                  # editor-only id; NOT Node.uuid
    nodetype: str                                  # "blue_node" | "orange_node"
    pos: Tuple[int, int]                           # minimap pixel coords (top-left origin)
    can_fall: bool = False
    fall_dist_exceeds_vertical_tp: bool = False
    is_left_platform_edge: bool = False
    is_right_platform_edge: bool = False


def read_editor_nodes(path: str) -> Result[Tuple[List[EditorNode], List[int]], str]:
    """
    Read a map CSV from `path`.

    Returns Success((nodes, rotation_order)) where:
      - nodes is the list of EditorNode in file order.
      - rotation_order is a list of local_ids of blue_nodes in file order.

    On any error returns Failure(<reason str>). Caller can decide UX.
    local_id starts at 1 and matches file row order (header excluded).
    """
    p = Path(path)
    if not p.exists():
        return Failure(f"File not found: {path}")
    try:
        with open(p, "r", newline="") as f:
            reader = csv.DictReader(f, delimiter=",")
            if reader.fieldnames != CSV_HEADER:
                return Failure(
                    f"CSV header mismatch. Expected {CSV_HEADER}, got {reader.fieldnames}"
                )
            nodes: List[EditorNode] = []
            rotation_order: List[int] = []
            for i, row in enumerate(reader, start=1):
                # Validate nodetype.
                nodetype = row["nodetype"]
                if nodetype not in VALID_NODETYPES:
                    return Failure(
                        f"Row {i + 1}: invalid nodetype {nodetype!r}, "
                        f"expected one of {sorted(VALID_NODETYPES)}"
                    )
                # Parse position.
                pos_raw = row["pos_in_minimap"]
                try:
                    pos = ast.literal_eval(pos_raw)
                except (ValueError, SyntaxError) as e:
                    return Failure(
                        f"Row {i + 1}: pos_in_minimap {pos_raw!r} not a valid literal: {e}"
                    )
                if not (
                    isinstance(pos, tuple)
                    and len(pos) == 2
                    and all(isinstance(c, int) for c in pos)
                ):
                    return Failure(
                        f"Row {i + 1}: pos_in_minimap {pos_raw!r} must be a 2-tuple of ints"
                    )
                # Parse booleans.
                bool_values: Dict[str, bool] = {}
                for field in BOOL_FIELDS:
                    cell = row[field]
                    if cell not in ("TRUE", "FALSE"):
                        return Failure(
                            f"Row {i + 1}: {field} must be TRUE or FALSE, got {cell!r}"
                        )
                    bool_values[field] = (cell == "TRUE")
                node = EditorNode(
                    local_id=i,
                    nodetype=nodetype,
                    pos=pos,
                    **bool_values,
                )
                nodes.append(node)
                if nodetype == "blue_node":
                    rotation_order.append(i)
            return Success((nodes, rotation_order))
    except OSError as e:
        return Failure(f"OS error reading {path}: {e}")


def write_editor_nodes(
    path: str,
    nodes: Dict[int, EditorNode],
    rotation_order: List[int],
) -> Result[None, str]:
    """
    Write editor nodes to a CSV at `path`.

    Row order: blue_nodes in rotation_order first, then orange_nodes by ascending local_id.
    Creates parent directory if it doesn't exist.
    """
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            writer = csv.writer(f, delimiter=",")
            writer.writerow(CSV_HEADER)
            for local_id in rotation_order:
                writer.writerow(_row_from_node(nodes[local_id]))
            for local_id in sorted(nodes.keys()):
                node = nodes[local_id]
                if node.nodetype == "orange_node":
                    writer.writerow(_row_from_node(node))
        return Success(None)
    except OSError as e:
        return Failure(f"OS error writing {path}: {e}")


def _row_from_node(node: EditorNode) -> List[str]:
    return [
        node.nodetype,
        f"({node.pos[0]}, {node.pos[1]})",
        "TRUE" if node.can_fall else "FALSE",
        "TRUE" if node.fall_dist_exceeds_vertical_tp else "FALSE",
        "TRUE" if node.is_left_platform_edge else "FALSE",
        "TRUE" if node.is_right_platform_edge else "FALSE",
    ]
