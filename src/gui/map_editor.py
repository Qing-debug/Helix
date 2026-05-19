"""
In-process map editor for placing/editing/ordering nodes against the live
minimap, producing CSVs the agent can load via Controller.loadMap.

The editor is a tk.Toplevel owned by MapleGUI. It subscribes to the same
SharedInfo.minimap_frame stream as the main GUI; each window owns its own
canvas and _updateCanvas loop.
"""

import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from PIL import Image, ImageTk
from src.controller.map_csv import EditorNode
from src.controller.node import Node
from src.controller.path_graph import PathGraph
from returns.pipeline import is_successful


RENDER_SCALE = 2  # minimap canvas + node coords rendered at this multiplier of native px

SELECT_RADIUS_PX = 3           # native coords; 6 px screen hit radius at RENDER_SCALE=2
NODE_DRAW_RADIUS_PX = 3        # native coords; 6 px screen radius / 12 px diameter at RENDER_SCALE=2
SELECTED_RING_RADIUS_PX = 1    # native coords; 2 px screen radius / 4 px diameter

FONT_BODY_SIZE = 10            # Tk default is 9pt; one above for slight legibility bump without crowding
FONT_HEADER_SIZE = 16
FONT_NODE_LABEL_SIZE = 7       # local_id text drawn next to blue-node dots on the minimap (not zoom-aware). Sized to roughly match the 12px on-screen dot diameter.
BUTTON_PADX = 12
BUTTON_PADY = 6
PANEL_PADX = 12
PANEL_PADY = 12
COLUMN_MIN_WIDTH_PX = 240      # fits the longest checkbox label ("fall_dist_exceeds_vertical_tp") at body size
SECTION_HEADER_FG = '#1a2b4a'  # dark navy; section-label hierarchy on the lightblue panel
NODE_LABEL_FG = 'white'        # local_id text color over the (typically dark) minimap

WINDOW_INITIAL_WIDTH = 800     # sized so the 3-column panel fits without clipping the rotation column
WINDOW_INITIAL_HEIGHT = 800

ZOOM_MIN = 0.5
ZOOM_MAX = 3.0
ZOOM_STEP = 0.1

CANVAS_TAG_NODE = "editor_node"
CANVAS_TAG_SELECTED = "editor_selected"
CANVAS_TAG_EDGE = "editor_edge"
CANVAS_TAG_BAND = "editor_band"


@dataclass
class MapEditorState:
    """Holds the editor's mutable state, isolated from the runtime PathGraph."""
    nodes: Dict[int, EditorNode] = field(default_factory=dict) 
    rotation_order: List[int] = field(default_factory=list)  # blue_node local_ids
    selected_id: Optional[int] = None
    next_local_id: int = 1                                   # monotonic
    placement_nodetype: str = "orange_node"                  # default for new placements
    current_file: Optional[str] = None
    dirty: bool = False                                      # any unsaved mutation since last save/load


class MapEditor:
    def __init__(self, parent_tk, controller, sharedInfo):
        """
        parent_tk:   the main GUI's tk.Tk instance (used as Toplevel parent).
        controller:  shared Controller, exposes tolerances and getCharacterCoords.
        sharedInfo:  shared minimap-frame buffer + lock.
        """
        self.controller = controller
        self.sharedInfo = sharedInfo
        self.state = MapEditorState()

        self.window = tk.Toplevel(parent_tk)
        self.window.title("Map Editor — untitled")
        self.window.geometry(f"{WINDOW_INITIAL_WIDTH}x{WINDOW_INITIAL_HEIGHT}")

        # Per-window zoom state and fonts. Per-instance tkfont.Font objects (not the global
        # named system fonts) so resizing them only affects widgets in this editor window.
        # Bindings live on self.window (not bind_all), so main GUI keystrokes don't trigger
        # editor zoom and vice versa.
        self.zoom_factor = 1.0
        self._base_font_sizes = {
            "body": FONT_BODY_SIZE,
            "header": FONT_HEADER_SIZE,
            "section": FONT_BODY_SIZE,
        }
        default_family = tkfont.nametofont("TkDefaultFont").cget("family")
        self._font_body = tkfont.Font(family=default_family, size=FONT_BODY_SIZE)
        self._font_header = tkfont.Font(family=default_family, size=FONT_HEADER_SIZE, weight="bold")
        self._font_section = tkfont.Font(family=default_family, size=FONT_BODY_SIZE, weight="bold")
        # Canvas-space label for blue-node local_ids; intentionally NOT in _base_font_sizes so it
        # doesn't scale with editor zoom (the minimap canvas itself is fixed-size, so labels are too).
        self._font_node_label = tkfont.Font(family=default_family, size=FONT_NODE_LABEL_SIZE, weight="bold")

        self.minimap_canvas = None
        self.minimap_canvas_bg_img_id = None
        self.minimap_canvas_width = None
        self.minimap_canvas_height = None

        self._buildLayout()
        self._bindZoomShortcuts()
        self._waitForMinimapAndBuildCanvas()
        self._updateCanvas()

    def _buildLayout(self):
        """Top frame holds the centered minimap canvas. Bottom frame holds a vertically-scrollable
        three-column controls panel (Placement defaults | Inspector | Rotation order).

        Wheel handling binds to self.window (NOT bind_all) so it stays scoped to this Toplevel;
        the main GUI keeps its own wheel handler unaffected.
        """
        self._canvas_frame = tk.Frame(self.window, bg='gray20')
        self._canvas_frame.pack(side=tk.TOP, fill=tk.X)

        panel_outer = tk.Frame(self.window, bg='lightblue')
        panel_outer.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)

        self._panel_canvas = tk.Canvas(
            panel_outer, bg='lightblue', highlightthickness=0, borderwidth=0,
        )
        panel_scrollbar = tk.Scrollbar(
            panel_outer, orient='vertical', command=self._panel_canvas.yview,
        )
        self._panel_canvas.configure(yscrollcommand=panel_scrollbar.set)
        self._panel_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        panel_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._panel_frame = tk.Frame(self._panel_canvas, bg='lightblue')
        panel_window_id = self._panel_canvas.create_window(
            (0, 0), window=self._panel_frame, anchor='nw',
        )
        self._panel_frame.bind(
            '<Configure>',
            lambda e: self._panel_canvas.configure(scrollregion=self._panel_canvas.bbox('all')),
        )
        self._panel_canvas.bind(
            '<Configure>',
            lambda e: self._panel_canvas.itemconfig(panel_window_id, width=e.width),
        )

        def _on_panel_wheel(event):
            widget = event.widget
            while widget is not None and widget is not self.window:
                if widget is panel_outer:
                    self._panel_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
                    return 'break'
                widget = widget.master
        self.window.bind('<MouseWheel>', _on_panel_wheel)

        tk.Label(
            self._panel_frame, text="Map Editor", bg='lightblue', font=self._font_header,
        ).grid(row=0, column=0, columnspan=3, pady=(PANEL_PADY, 8), sticky='ew')

        # Three equal-width column bays. minsize keeps the longest checkbox label legible even
        # if the user shrinks the window narrower than the natural 3-column width.
        for c in range(3):
            self._panel_frame.grid_columnconfigure(
                c, weight=1, uniform='cols', minsize=COLUMN_MIN_WIDTH_PX,
            )

        placement_col = tk.Frame(self._panel_frame, bg='lightblue')
        placement_col.grid(row=1, column=0, padx=PANEL_PADX, pady=4, sticky='nsew')
        inspector_col = tk.Frame(self._panel_frame, bg='lightblue')
        inspector_col.grid(row=1, column=1, padx=PANEL_PADX, pady=4, sticky='nsew')
        rotation_col = tk.Frame(self._panel_frame, bg='lightblue')
        rotation_col.grid(row=1, column=2, padx=PANEL_PADX, pady=4, sticky='nsew')

        # Sticky flag defaults baked into newly-placed nodes. Independent from the inspector's
        # flag checkboxes (which edit the selected node). Lets the user batch-place a run of
        # nodes that all share a flag config without ticking it per-node.
        tk.Label(
            placement_col, text="Placement defaults",
            bg='lightblue', fg=SECTION_HEADER_FG, font=self._font_section,
        ).pack(anchor='w', pady=(0, 4))

        self._placement_var = tk.StringVar(value="orange_node")
        for label, value in (("blue_node", "blue_node"), ("orange_node", "orange_node")):
            tk.Radiobutton(
                placement_col, text=label, variable=self._placement_var, value=value,
                bg='lightblue', font=self._font_body, command=self._onPlacementChange,
            ).pack(anchor='w', padx=PANEL_PADX)

        self._placement_flag_vars = {
            "can_fall": tk.BooleanVar(),
            "fall_dist_exceeds_vertical_tp": tk.BooleanVar(),
            "is_left_platform_edge": tk.BooleanVar(),
            "is_right_platform_edge": tk.BooleanVar(),
        }
        for field_name, var in self._placement_flag_vars.items():
            tk.Checkbutton(
                placement_col, text=field_name, variable=var,
                bg='lightblue', font=self._font_body,
            ).pack(anchor='w', padx=PANEL_PADX)

        tk.Label(
            inspector_col, text="Inspector",
            bg='lightblue', fg=SECTION_HEADER_FG, font=self._font_section,
        ).pack(anchor='w', pady=(0, 4))

        self._inspector_pos_label = tk.Label(
            inspector_col, text="pos: —", bg='lightblue', font=self._font_body,
        )
        self._inspector_pos_label.pack(anchor='w')

        self._inspector_nodetype_var = tk.StringVar(value="orange_node")
        nodetype_row = tk.Frame(inspector_col, bg='lightblue')
        nodetype_row.pack(anchor='w')
        for label, value in (("blue", "blue_node"), ("orange", "orange_node")):
            tk.Radiobutton(
                nodetype_row, text=label, variable=self._inspector_nodetype_var, value=value,
                bg='lightblue', font=self._font_body, command=self._onInspectorNodetypeChange,
            ).pack(side=tk.LEFT)

        self._inspector_flag_vars = {
            "can_fall": tk.BooleanVar(),
            "fall_dist_exceeds_vertical_tp": tk.BooleanVar(),
            "is_left_platform_edge": tk.BooleanVar(),
            "is_right_platform_edge": tk.BooleanVar(),
        }
        for field_name, var in self._inspector_flag_vars.items():
            tk.Checkbutton(
                inspector_col, text=field_name, variable=var,
                bg='lightblue', font=self._font_body,
                command=lambda f=field_name: self._onInspectorFlagChange(f),
            ).pack(anchor='w')

        tk.Button(
            inspector_col, text="Delete", font=self._font_body,
            padx=BUTTON_PADX, pady=BUTTON_PADY, command=self._deleteSelected,
        ).pack(anchor='w', pady=(4, 0))

        tk.Label(
            rotation_col, text="Rotation order",
            bg='lightblue', fg=SECTION_HEADER_FG, font=self._font_section,
        ).pack(anchor='w', pady=(0, 4))
        self._rotation_frame = tk.Frame(rotation_col, bg='lightblue')
        self._rotation_frame.pack(fill=tk.X)

        self._show_edges_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            self._panel_frame,
            text="Show edges",
            variable=self._show_edges_var,
            bg='lightblue', font=self._font_body,
            command=self._renderPreview,
        ).grid(row=2, column=0, columnspan=3, sticky='w', padx=PANEL_PADX, pady=(12, 0))

    def _waitForMinimapAndBuildCanvas(self):
        """
        Poll sharedInfo for a non-None minimap frame, then build the editor's
        own Canvas at minimap's native dimensions. Mirrors MapleGUI's pattern.

        Uses tk.after polling rather than time.sleep so the Tk event loop
        stays responsive while we wait.
        """
        with self.sharedInfo.minimap_frame_lock:
            frame = self.sharedInfo.minimap_frame
        if frame is None:
            self.window.after(200, self._waitForMinimapAndBuildCanvas)
            return
        h, w, _ = frame.shape
        self.minimap_canvas_height = h * RENDER_SCALE
        self.minimap_canvas_width = w * RENDER_SCALE
        self.minimap_canvas = tk.Canvas(
            self._canvas_frame,
            width=self.minimap_canvas_width,
            height=self.minimap_canvas_height,
            background='pink',
            highlightthickness=0,
            borderwidth=0,
            relief='flat',
        )
        self.minimap_canvas.pack(padx=8, pady=8)  # default side=TOP centers horizontally in the frame
        self.minimap_canvas.bind("<Button-1>", self._onCanvasClick)
        self.window.bind("<Delete>", lambda e: self._deleteSelected())
        self._refreshInspector()  # start with empty inspector since no node is selected yet
        self._refreshRotation()

    def _onPlacementChange(self):
        self.state.placement_nodetype = self._placement_var.get()

    def _onInspectorNodetypeChange(self):
        sid = self.state.selected_id
        if sid is None or sid not in self.state.nodes:
            return
        new_type = self._inspector_nodetype_var.get()
        node = self.state.nodes[sid]
        if node.nodetype == new_type:
            return
        old_type = node.nodetype
        node.nodetype = new_type
        if old_type == "blue_node" and sid in self.state.rotation_order:
            self.state.rotation_order.remove(sid)
        if new_type == "blue_node" and sid not in self.state.rotation_order:
            self.state.rotation_order.append(sid)
        self._markDirty()
        self._refreshInspector()
        self._renderNodes()
        self._refreshRotation()

    def _onInspectorFlagChange(self, field_name):
        sid = self.state.selected_id
        if sid is None or sid not in self.state.nodes:
            return
        node = self.state.nodes[sid]
        setattr(node, field_name, bool(self._inspector_flag_vars[field_name].get()))
        self._markDirty()
        self._renderNodes()  # is_left/right_platform_edge affect vertical edge validity

    def _refreshInspector(self):
        """Sync inspector widgets to the currently selected node."""
        sid = self.state.selected_id
        if sid is None or sid not in self.state.nodes:
            self._inspector_pos_label.config(text="pos: —")
            self._inspector_nodetype_var.set("orange_node")
            for var in self._inspector_flag_vars.values():
                var.set(False)
            return
        node = self.state.nodes[sid]
        self._inspector_pos_label.config(text=f"pos: {node.pos}")
        self._inspector_nodetype_var.set(node.nodetype)
        for field_name, var in self._inspector_flag_vars.items():
            var.set(getattr(node, field_name))

    def _refreshRotation(self):
        """Rebuild the rotation order list widgets from current state."""
        for child in self._rotation_frame.winfo_children():
            child.destroy()
        for idx, local_id in enumerate(self.state.rotation_order):
            node = self.state.nodes[local_id]
            row = tk.Frame(self._rotation_frame, bg='lightblue')
            row.pack(fill=tk.X)
            tk.Label(
                row,
                text=f"{idx + 1}. #{local_id} {node.pos}",
                bg='lightblue',
                font=self._font_body,
            ).pack(side=tk.LEFT)
            tk.Button(
                row, text="↑", width=2,
                font=self._font_body,
                command=lambda i=idx: self._moveRotation(i, -1),
            ).pack(side=tk.RIGHT)
            tk.Button(
                row, text="↓", width=2,
                font=self._font_body,
                command=lambda i=idx: self._moveRotation(i, +1),
            ).pack(side=tk.RIGHT)

    def _moveRotation(self, idx, delta):
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(self.state.rotation_order):
            return
        order = self.state.rotation_order
        order[idx], order[new_idx] = order[new_idx], order[idx]
        self._markDirty()
        self._refreshRotation()

    def _applyZoom(self):
        """Resize this editor's Font objects in place. Widgets referencing them auto-update."""
        for key, font_obj in (
            ("body", self._font_body),
            ("header", self._font_header),
            ("section", self._font_section),
        ):
            base = self._base_font_sizes[key]
            font_obj.configure(size=max(1, int(round(base * self.zoom_factor))))

    def _zoomIn(self, event=None):
        self.zoom_factor = min(ZOOM_MAX, self.zoom_factor + ZOOM_STEP)
        self._applyZoom()
        return 'break'

    def _zoomOut(self, event=None):
        self.zoom_factor = max(ZOOM_MIN, self.zoom_factor - ZOOM_STEP)
        self._applyZoom()
        return 'break'

    def _zoomReset(self, event=None):
        self.zoom_factor = 1.0
        self._applyZoom()
        return 'break'

    def _onCtrlMouseWheel(self, event):
        if event.delta > 0:
            self._zoomIn()
        else:
            self._zoomOut()
        return 'break'

    def _bindZoomShortcuts(self):
        """Scope zoom to this editor's Toplevel only — main GUI and other Toplevels unaffected."""
        self.window.bind('<Control-plus>', self._zoomIn)
        self.window.bind('<Control-equal>', self._zoomIn)
        self.window.bind('<Control-KP_Add>', self._zoomIn)
        self.window.bind('<Control-minus>', self._zoomOut)
        self.window.bind('<Control-KP_Subtract>', self._zoomOut)
        self.window.bind('<Control-0>', self._zoomReset)
        self.window.bind('<Control-MouseWheel>', self._onCtrlMouseWheel)

    def _onCanvasClick(self, event):
        """Left-click on canvas: select an existing node within SELECT_RADIUS_PX, else place a new one.

        event.x/event.y are in canvas pixels (post-scale); divide by RENDER_SCALE to get
        native minimap coords for storage and hit-testing.
        """
        native_x = event.x // RENDER_SCALE
        native_y = event.y // RENDER_SCALE
        hit_id = self._findNodeAt(native_x, native_y)
        if hit_id is not None:
            self.state.selected_id = hit_id
        else:
            self._placeNode(native_x, native_y)
            self._markDirty()
            self._refreshRotation()
        self._refreshInspector()
        self._renderNodes()

    def _findNodeAt(self, x, y):
        """Return local_id of the first node within SELECT_RADIUS_PX of (x, y), or None."""
        for node in self.state.nodes.values():
            nx, ny = node.pos
            if (nx - x) ** 2 + (ny - y) ** 2 <= SELECT_RADIUS_PX ** 2:
                return node.local_id
        return None

    def _placeNode(self, x, y):
        """Create a new EditorNode at (x, y) using the current placement nodetype + sticky flag defaults. Auto-selects it."""
        local_id = self.state.next_local_id
        self.state.next_local_id += 1
        flag_kwargs = {name: bool(var.get()) for name, var in self._placement_flag_vars.items()}
        node = EditorNode(
            local_id=local_id,
            nodetype=self.state.placement_nodetype,
            pos=(int(x), int(y)),
            **flag_kwargs,
        )
        self.state.nodes[local_id] = node
        if node.nodetype == "blue_node":
            self.state.rotation_order.append(local_id)
        self.state.selected_id = local_id

    def _deleteSelected(self):
        sid = self.state.selected_id
        if sid is None or sid not in self.state.nodes:
            return
        del self.state.nodes[sid]
        if sid in self.state.rotation_order:
            self.state.rotation_order.remove(sid)
        self.state.selected_id = None
        self._markDirty()
        self._refreshInspector()
        self._renderNodes()
        self._refreshRotation()

    def _markDirty(self):
        if not self.state.dirty:
            self.state.dirty = True
            # title bar update lands in Task 14 — placeholder for now
            self._refreshTitle()

    def _refreshTitle(self):
        """Composes the title bar. Body is a placeholder until Task 14 ties Save state in."""
        prefix = "* " if self.state.dirty else ""
        name = self.state.current_file or "untitled"
        self.window.title(f"{prefix}{name} — Map Editor")

    def _buildPreviewGraph(self):
        """
        Build a throwaway PathGraph that matches what the runtime would build after
        a save → load cycle of the current editor state.

        Insertion order into node_map mirrors map_csv.write_editor_nodes: rotation-order
        blue_nodes first, then orange_nodes sorted by local_id. This matters because
        PathGraph._findClosest* methods break distance ties by keeping the first-inserted
        candidate (strict `>` comparison), so iteration order can flip edges in tie cases.

        Returns (path_graph, id_to_node) where id_to_node maps each EditorNode's
        local_id to the Node instance built for the preview. Bumps Node.node_id_counter
        every call — accepted tradeoff documented under Task 12 in the plan; UUIDs are
        runtime-only and not persisted.
        """
        order = list(self.state.rotation_order)
        order += sorted(
            lid for lid, n in self.state.nodes.items()
            if n.nodetype != "blue_node"
        )
        id_to_node = {}
        node_map = {}
        for local_id in order:
            editor_node = self.state.nodes[local_id]
            n = Node(
                nodetype=editor_node.nodetype,
                minimap_pos=editor_node.pos,
                can_fall=editor_node.can_fall,
                fall_dist_exceeds_vertical_tp=editor_node.fall_dist_exceeds_vertical_tp,
                is_left_platform_edge=editor_node.is_left_platform_edge,
                is_right_platform_edge=editor_node.is_right_platform_edge,
            )
            node_map[n.uuid] = n
            id_to_node[editor_node.local_id] = n
        path_graph = PathGraph(
            node_map=node_map,
            edge_y_alignment_allowance=self.controller.agent.edge_y_tolerance_level,
            edge_x_alignment_allowance=self.controller.agent.edge_x_tolerance_level,
        )
        build_res = path_graph.buildGraph()
        if not is_successful(build_res):
            # Empty editor returns Failure("Node_dict is empty.") — just return no edges.
            return path_graph, id_to_node
        return path_graph, id_to_node

    def _renderPreview(self):
        """Render preview overlays (edges now; bands in Task 13). Called whenever toggles or state change."""
        if self.minimap_canvas is None:
            return
        self.minimap_canvas.delete(CANVAS_TAG_EDGE)
        self.minimap_canvas.delete(CANVAS_TAG_BAND)
        if not self._show_edges_var.get():
            return
        path_graph, id_to_node = self._buildPreviewGraph()
        if not id_to_node:
            return
        # Classify edges horizontal vs vertical by Δy vs Δx; minimap_position is native
        # coords, multiply by RENDER_SCALE for canvas pixels (same pattern as _renderNodes).
        # Dedupe by unordered pair so one line renders per pair; arrowheads encode which
        # directed edges actually exist (asymmetric vertical edges with platform-edge gating
        # would otherwise look bidirectional to the eye — see _isVerticalEdgeValid).
        drawn = set()
        for u, v in path_graph.graph.edges():
            key = frozenset((u, v))
            if key in drawn:
                continue
            drawn.add(key)
            has_uv = path_graph.graph.has_edge(u, v)
            has_vu = path_graph.graph.has_edge(v, u)
            if has_uv and has_vu:
                arrow_spec = tk.BOTH
            elif has_uv:
                arrow_spec = tk.LAST
            else:
                arrow_spec = tk.FIRST
            ux, uy = u.minimap_position
            vx, vy = v.minimap_position
            is_vertical = abs(vy - uy) > abs(vx - ux)
            color = "gray20" if is_vertical else "gray60"
            sx1, sy1 = ux * RENDER_SCALE, uy * RENDER_SCALE
            sx2, sy2 = vx * RENDER_SCALE, vy * RENDER_SCALE
            self.minimap_canvas.create_line(
                sx1, sy1, sx2, sy2,
                fill=color, width=1, arrow=arrow_spec,
                tags=CANVAS_TAG_EDGE,
            )

    def _renderNodes(self):
        """Redraw all nodes + the selected-ring overlay. Calls _renderPreview first so
        node dots sit on top of edge/band overlays.

        node.pos is in native minimap coords; multiply by RENDER_SCALE for canvas pixels.
        """
        if self.minimap_canvas is None:
            return
        self._renderPreview()
        self.minimap_canvas.delete(CANVAS_TAG_NODE)
        self.minimap_canvas.delete(CANVAS_TAG_SELECTED)
        node_r = NODE_DRAW_RADIUS_PX * RENDER_SCALE
        for node in self.state.nodes.values():
            x, y = node.pos
            sx, sy = x * RENDER_SCALE, y * RENDER_SCALE
            fill = "lightblue" if node.nodetype == "blue_node" else "orange"
            outline = "blue" if node.nodetype == "blue_node" else "darkorange"
            self.minimap_canvas.create_oval(
                sx - node_r, sy - node_r,
                sx + node_r, sy + node_r,
                fill=fill, outline=outline, width=1,
                tags=CANVAS_TAG_NODE,
            )
            if node.nodetype == "blue_node":
                self.minimap_canvas.create_text(
                    sx + node_r + 2, sy,
                    text=f"#{node.local_id}",
                    anchor='w',
                    fill=NODE_LABEL_FG,
                    font=self._font_node_label,
                    tags=CANVAS_TAG_NODE,
                )
        if self.state.selected_id is not None and self.state.selected_id in self.state.nodes:
            x, y = self.state.nodes[self.state.selected_id].pos
            sx, sy = x * RENDER_SCALE, y * RENDER_SCALE
            ring_r = SELECTED_RING_RADIUS_PX * RENDER_SCALE
            self.minimap_canvas.create_oval(
                sx - ring_r, sy - ring_r,
                sx + ring_r, sy + ring_r,
                fill="", outline="yellow", width=2,
                tags=CANVAS_TAG_SELECTED,
            )

    def _updateCanvas(self):
        """
        Pull the latest minimap frame and draw it. Schedules itself every 10ms
        via tk.after, matching MapleGUI._updateCanvas's cadence. Stops when the
        editor window has been destroyed.
        """
        if not self.window.winfo_exists():
            return  # window destroyed — stop the loop
        if self.minimap_canvas is None:
            self.window.after(10, self._updateCanvas)
            return
        with self.sharedInfo.minimap_frame_lock:
            frame = self.sharedInfo.minimap_frame
            if frame is not None:
                pil_minimap = Image.fromarray(frame)
                if RENDER_SCALE != 1:
                    pil_minimap = pil_minimap.resize(
                        (self.minimap_canvas_width, self.minimap_canvas_height),
                        Image.NEAREST,  # game pixels stay sharp; no interpolation blur
                    )
                minimap_img = ImageTk.PhotoImage(pil_minimap)
                self.minimap_canvas.image = minimap_img  # prevent GC
                if self.minimap_canvas_bg_img_id is None:
                    self.minimap_canvas_bg_img_id = self.minimap_canvas.create_image(
                        0, 0, image=minimap_img, anchor=tk.NW
                    )
                else:
                    self.minimap_canvas.itemconfig(
                        self.minimap_canvas_bg_img_id, image=minimap_img
                    )
        self.window.after(10, self._updateCanvas)
