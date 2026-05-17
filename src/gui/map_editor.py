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


RENDER_SCALE = 2  # minimap canvas + node coords rendered at this multiplier of native px

SELECT_RADIUS_PX = 3           # native coords; 6 px screen hit radius at RENDER_SCALE=2
NODE_DRAW_RADIUS_PX = 3        # native coords; 6 px screen radius / 12 px diameter at RENDER_SCALE=2
SELECTED_RING_RADIUS_PX = 1    # native coords; 2 px screen radius / 4 px diameter

FONT_BODY_SIZE = 13            # default is 9pt; ~1.44x for "scaled-up" feel
FONT_HEADER_SIZE = 16
BUTTON_PADX = 12
BUTTON_PADY = 6
PANEL_PADX = 12
PANEL_PADY = 12

ZOOM_MIN = 0.5
ZOOM_MAX = 3.0
ZOOM_STEP = 0.1

CANVAS_TAG_NODE = "editor_node"
CANVAS_TAG_SELECTED = "editor_selected"


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

        # Per-window zoom state and fonts. Per-instance tkfont.Font objects (not the global
        # named system fonts) so resizing them only affects widgets in this editor window.
        # Bindings live on self.window (not bind_all), so main GUI keystrokes don't trigger
        # editor zoom and vice versa.
        self.zoom_factor = 1.0
        self._base_font_sizes = {"body": FONT_BODY_SIZE, "header": FONT_HEADER_SIZE}
        default_family = tkfont.nametofont("TkDefaultFont").cget("family")
        self._font_body = tkfont.Font(family=default_family, size=FONT_BODY_SIZE)
        self._font_header = tkfont.Font(family=default_family, size=FONT_HEADER_SIZE, weight="bold")

        self.minimap_canvas = None
        self.minimap_canvas_bg_img_id = None
        self.minimap_canvas_width = None
        self.minimap_canvas_height = None

        self._buildLayout()
        self._bindZoomShortcuts()
        self._waitForMinimapAndBuildCanvas()
        self._updateCanvas()

    def _buildLayout(self):
        """Top frame holds the centered minimap canvas. Bottom frame holds full-width controls."""
        self._canvas_frame = tk.Frame(self.window, bg='gray20')
        self._canvas_frame.pack(side=tk.TOP, fill=tk.X)

        self._panel_frame = tk.Frame(self.window, bg='lightblue')
        self._panel_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)

        tk.Label(self._panel_frame, text="Map Editor", bg='lightblue',
                 font=self._font_header).pack(pady=(PANEL_PADY, 4))

        self._placement_var = tk.StringVar(value="orange_node")
        tk.Label(self._panel_frame, text="Placement defaults", bg='lightblue',
                 font=self._font_body).pack(anchor='w', padx=PANEL_PADX, pady=(8, 0))
        for label, value in (("blue_node", "blue_node"), ("orange_node", "orange_node")):
            tk.Radiobutton(
                self._panel_frame,
                text=label,
                variable=self._placement_var,
                value=value,
                bg='lightblue',
                font=self._font_body,
                command=self._onPlacementChange,
            ).pack(anchor='w', padx=PANEL_PADX * 2)

        tk.Label(self._panel_frame, text="Inspector", bg='lightblue',
                 font=self._font_body).pack(anchor='w', padx=PANEL_PADX, pady=(12, 0))
        self._inspector_frame = tk.Frame(self._panel_frame, bg='lightblue')
        self._inspector_frame.pack(fill=tk.X, padx=PANEL_PADX)

        self._inspector_pos_label = tk.Label(
            self._inspector_frame, text="pos: —", bg='lightblue', font=self._font_body
        )
        self._inspector_pos_label.pack(anchor='w')

        self._inspector_nodetype_var = tk.StringVar(value="orange_node")
        self._inspector_nodetype_frame = tk.Frame(self._inspector_frame, bg='lightblue')
        self._inspector_nodetype_frame.pack(anchor='w')
        for label, value in (("blue", "blue_node"), ("orange", "orange_node")):
            tk.Radiobutton(
                self._inspector_nodetype_frame,
                text=label,
                variable=self._inspector_nodetype_var,
                value=value,
                bg='lightblue',
                font=self._font_body,
                command=self._onInspectorNodetypeChange,
            ).pack(side=tk.LEFT)

        self._inspector_flag_vars = {
            "can_fall": tk.BooleanVar(),
            "fall_dist_exceeds_vertical_tp": tk.BooleanVar(),
            "is_left_platform_edge": tk.BooleanVar(),
            "is_right_platform_edge": tk.BooleanVar(),
        }
        for field_name, var in self._inspector_flag_vars.items():
            tk.Checkbutton(
                self._inspector_frame,
                text=field_name,
                variable=var,
                bg='lightblue',
                font=self._font_body,
                command=lambda f=field_name: self._onInspectorFlagChange(f),
            ).pack(anchor='w')

        self._inspector_delete_btn = tk.Button(
            self._inspector_frame,
            text="Delete",
            font=self._font_body,
            padx=BUTTON_PADX, pady=BUTTON_PADY,
            command=self._deleteSelected,
        )
        self._inspector_delete_btn.pack(anchor='w', pady=(4, 0))

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

    def _onInspectorFlagChange(self, field_name):
        sid = self.state.selected_id
        if sid is None or sid not in self.state.nodes:
            return
        node = self.state.nodes[sid]
        setattr(node, field_name, bool(self._inspector_flag_vars[field_name].get()))
        self._markDirty()
        # No re-render needed for flag changes alone; preview rendering (Task 12) will hook in here.

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

    def _applyZoom(self):
        """Resize this editor's Font objects in place. Widgets referencing them auto-update."""
        for key, font_obj in (("body", self._font_body), ("header", self._font_header)):
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
        """Create a new EditorNode at (x, y) using the current placement nodetype. Auto-selects it."""
        local_id = self.state.next_local_id
        self.state.next_local_id += 1
        node = EditorNode(
            local_id=local_id,
            nodetype=self.state.placement_nodetype,
            pos=(int(x), int(y)),
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

    def _renderNodes(self):
        """Redraw all nodes + the selected-ring overlay. Edges/bands land in Tasks 12-13.

        node.pos is in native minimap coords; multiply by RENDER_SCALE for canvas pixels.
        """
        if self.minimap_canvas is None:
            return
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
