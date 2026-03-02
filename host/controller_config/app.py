"""Main application window for the controller configuration tool.

Ties together the action panel, controller canvas, and binding dialog
with a menu bar and controller tabs.
"""

import json
import time
import tkinter as tk
from copy import deepcopy
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

import sys

# Ensure project root is on the path so utils.controller can be imported
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Default directory for file dialogs (data/ relative to repo root)
_default_data_dir = _project_root / "data"

# Settings file to remember last opened config
_settings_file = Path(__file__).resolve().parent / ".settings.json"

from utils.controller.model import FullConfig, ControllerConfig, InputType
from utils.controller.config_io import (
    load_actions_from_file,
    load_config,
    save_actions_to_file,
    save_assignments_to_file,
    save_config,
)

from .action_panel import ActionPanel
from .binding_dialog import BindingDialog
from .controller_canvas import ControllerCanvas
from .import_dialog import ImportConflictDialog
from .layout_coords import XBOX_INPUT_MAP
from .print_render import export_pages


def load_settings() -> dict:
    """Load app settings from the settings file.

    Usable without instantiating the GUI (e.g. from CLI).
    """
    try:
        if _settings_file.exists():
            return json.loads(_settings_file.read_text())
    except (json.JSONDecodeError, OSError):
        pass  # Corrupt or missing settings file; fall back to defaults
    return {}

# Maps controller input type (str from layout_coords) to compatible action
# InputType values.  POV inputs are treated as boolean (button) since the
# angle is filtered to a boolean at runtime.  POV action type is also
# treated as BUTTON for now.
_COMPAT_ACTION_TYPES: dict[str, set[InputType]] = {
    "button": {InputType.BUTTON, InputType.POV},
    "axis":   {InputType.ANALOG},
    "output": {InputType.OUTPUT},
    "pov":    {InputType.BUTTON, InputType.POV},
}

# Human-readable descriptions of what each input type accepts
_INPUT_TYPE_DESCRIPTION: dict[str, str] = {
    "button": "Button inputs accept Button actions",
    "axis":   "Axis inputs accept Analog actions",
    "output": "Output inputs accept Output actions",
    "pov":    "POV inputs accept Button actions (treated as boolean)",
}


class _UnsavedChangesDialog(tk.Toplevel):
    """Modal dialog offering Save / Save As / Discard / Cancel."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Unsaved Changes")
        self.resizable(False, False)
        self.result: str = "cancel"

        self.transient(parent)
        self.grab_set()

        # Message
        ttk.Label(
            self, text="You have unsaved changes. What would you like to do?",
            padding=(20, 15, 20, 10),
        ).pack()

        # Buttons
        btn_frame = ttk.Frame(self, padding=(10, 5, 10, 15))
        btn_frame.pack()

        ttk.Button(btn_frame, text="Save",
                   command=lambda: self._choose("save"),
                   width=14).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Save As...",
                   command=lambda: self._choose("save_as"),
                   width=14).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Discard Changes",
                   command=lambda: self._choose("discard"),
                   width=14).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel",
                   command=lambda: self._choose("cancel"),
                   width=14).pack(side=tk.LEFT, padx=4)

        self.protocol("WM_DELETE_WINDOW", lambda: self._choose("cancel"))
        self.bind("<Escape>", lambda e: self._choose("cancel"))

        # Center on parent
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

        self.wait_window()

    def _choose(self, choice: str):
        self.result = choice
        self.destroy()


class ControllerConfigApp(tk.Tk):
    """Main application window."""

    def __init__(self, initial_file: str | None = None):
        # Set app ID so Windows taskbar shows our icon instead of python.exe
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "raptacon.controller_config")
        except (AttributeError, OSError):
            pass  # Not on Windows or missing API

        super().__init__()
        self.title("FRC Controller Configuration")
        self.geometry("1200x700")
        self.minsize(900, 550)

        self._config = FullConfig()
        self._current_file: Path | None = None
        self._dirty = False
        self._settings = self._load_settings()

        # Restore saved window geometry (size + position)
        saved_geom = self._settings.get("geometry")
        if saved_geom:
            self.geometry(saved_geom)

        # Window icon (title bar + taskbar)
        icon_path = _project_root / "images" / "Raptacon3200-BG-BW.png"
        if icon_path.exists():
            self._icon_image = tk.PhotoImage(file=str(icon_path))
            self.iconphoto(True, self._icon_image)

        # Undo / redo stacks: each entry is (FullConfig, empty_groups_set)
        self._undo_stack: list[tuple[FullConfig, set[str]]] = []
        self._redo_stack: list[tuple[FullConfig, set[str]]] = []
        self._last_undo_time: float = 0.0
        self._restoring: bool = False  # Guard against spurious pushes

        # Drag-and-drop state
        self._drag_action: str | None = None
        self._drag_bindings_saved: dict = {}  # saved bind_all IDs

        self._build_menu()
        self._build_layout()

        # Load initial file, last opened file, or set up defaults
        if initial_file:
            self._open_file(Path(initial_file))
        elif self._settings.get("last_file"):
            last = Path(self._settings["last_file"])
            if last.exists():
                self._open_file(last)
            else:
                self._new_config()
        else:
            self._new_config()

        self._update_title()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New", command=self._new_config, accelerator="Ctrl+N")
        file_menu.add_command(label="Open...", command=self._open_dialog, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Save", command=self._save, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As...", command=self._save_as, accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="Import Actions...",
                              command=self._import_actions, accelerator="Ctrl+I")
        file_menu.add_separator()
        file_menu.add_command(label="Export All Groups...",
                              command=self._export_all_groups)
        file_menu.add_command(label="Export Assignments...",
                              command=self._export_assignments)
        file_menu.add_separator()
        print_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Print / Export", menu=print_menu)
        print_menu.add_command(
            label="Portrait (2 per page) - PNG...",
            command=lambda: self._print_export("portrait", "png"))
        print_menu.add_command(
            label="Portrait (2 per page) - PDF...",
            command=lambda: self._print_export("portrait", "pdf"))
        print_menu.add_command(
            label="Landscape (1 per page) - PNG...",
            command=lambda: self._print_export("landscape", "png"))
        print_menu.add_command(
            label="Landscape (1 per page) - PDF...",
            command=lambda: self._print_export("landscape", "pdf"))
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)

        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Undo", command=self._undo,
                              accelerator="Ctrl+Z")
        edit_menu.add_command(label="Redo", command=self._redo,
                              accelerator="Ctrl+Y")

        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        self._show_borders_var = tk.BooleanVar(
            value=self._settings.get("show_borders", False))
        view_menu.add_checkbutton(label="Show Button Borders",
                                  variable=self._show_borders_var,
                                  command=self._toggle_borders)
        self._lock_labels_var = tk.BooleanVar(value=False)
        view_menu.add_checkbutton(label="Lock Label Positions",
                                  variable=self._lock_labels_var,
                                  command=self._toggle_lock_labels)
        self._hide_unassigned_var = tk.BooleanVar(value=False)
        view_menu.add_checkbutton(label="Hide Unassigned Inputs",
                                  variable=self._hide_unassigned_var,
                                  command=self._toggle_hide_unassigned)
        view_menu.add_command(label="Reset Label Positions",
                              command=self._reset_label_positions)

        self.bind_all("<Control-n>", lambda e: self._new_config())
        self.bind_all("<Control-o>", lambda e: self._open_dialog())
        self.bind_all("<Control-s>", lambda e: self._save())
        self.bind_all("<Control-Shift-S>", lambda e: self._save_as())
        self.bind_all("<Control-i>", lambda e: self._import_actions())
        self.bind_all("<Control-z>", lambda e: self._undo())
        self.bind_all("<Control-y>", lambda e: self._redo())

    def _build_layout(self):
        # Main horizontal pane: action panel (left) | controller tabs (right)
        self._paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self._paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left: Action panel
        self._action_panel = ActionPanel(
            self._paned,
            on_actions_changed=self._on_actions_changed,
            on_export_group=self._export_group,
            on_drag_start=self._on_drag_start,
            on_drag_end=self._on_drag_end,
            on_before_change=self._on_before_action_change,
            get_binding_info=self._get_binding_info_for_action,
            on_assign_action=self._context_assign_action,
            on_unassign_action=self._context_unassign_action,
            on_unassign_all=self._context_unassign_all,
            get_all_controllers=self._get_all_controllers,
            get_compatible_inputs=self._get_compatible_inputs_with_display,
            is_action_bound=self._is_action_bound_to,
            on_action_renamed=self._on_action_renamed,
        )
        self._paned.add(self._action_panel, weight=0)

        # Right: Controller tabs + add button
        right_frame = ttk.Frame(self._paned)
        self._paned.add(right_frame, weight=1)

        tab_toolbar = ttk.Frame(right_frame)
        tab_toolbar.pack(fill=tk.X)
        ttk.Button(tab_toolbar, text="+ Add Controller", command=self._add_controller_tab).pack(
            side=tk.RIGHT, padx=5, pady=2)
        ttk.Button(tab_toolbar, text="- Remove Controller", command=self._remove_controller_tab).pack(
            side=tk.RIGHT, padx=5, pady=2)

        self._notebook = ttk.Notebook(right_frame)
        self._notebook.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        self._controller_canvases: dict[int, ControllerCanvas] = {}

        # Status bar
        self._hover_status_active = False
        self._status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self, textvariable=self._status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=2)

    # --- Settings Persistence ---

    @staticmethod
    def _load_settings() -> dict:
        """Load app settings (last opened file, etc.)."""
        return load_settings()

    def _save_settings(self):
        """Persist app settings."""
        try:
            _settings_file.write_text(json.dumps(self._settings, indent=2))
        except OSError:
            pass  # Non-fatal: settings are convenience, not critical

    def _get_initial_dir(self) -> str:
        """Return the best initial directory for file dialogs."""
        # Use the directory of the current file if one is open
        if self._current_file and self._current_file.parent.exists():
            return str(self._current_file.parent)
        # Fall back to data/ in the repo
        if _default_data_dir.exists():
            return str(_default_data_dir)
        return str(_project_root)

    # --- Config Management ---

    def _new_config(self):
        """Create a new blank configuration with two default controllers."""
        if self._dirty and not self._handle_unsaved_changes():
            return

        self._config = FullConfig(
            controllers={
                0: ControllerConfig(port=0, name="Driver"),
                1: ControllerConfig(port=1, name="Operator"),
            }
        )
        self._current_file = None
        self._dirty = False
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._sync_ui_from_config()
        self._update_title()
        self._status_var.set("New configuration created")

    def _open_dialog(self):
        if self._dirty and not self._handle_unsaved_changes():
            return

        path = filedialog.askopenfilename(
            title="Open Controller Config",
            initialdir=self._get_initial_dir(),
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
        )
        if path:
            self._open_file(Path(path))

    def _open_file(self, path: Path):
        try:
            self._config = load_config(path)
            self._current_file = path.resolve()
            self._dirty = False
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._sync_ui_from_config()
            self._update_title()
            self._status_var.set(f"Opened: {path.name}")
            self._settings["last_file"] = str(self._current_file)
            self._save_settings()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file:\n{e}")

    def _save(self):
        if self._current_file:
            self._save_to(self._current_file)
        else:
            self._save_as()

    def _save_as(self):
        path = filedialog.asksaveasfilename(
            title="Save Controller Config",
            initialdir=self._get_initial_dir(),
            defaultextension=".yaml",
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
        )
        if path:
            self._save_to(Path(path))

    def _save_to(self, path: Path):
        try:
            self._sync_config_from_ui()
            save_config(self._config, path)
            self._current_file = path.resolve()
            self._dirty = False
            self._update_title()
            self._status_var.set(f"Saved: {path.name}")
            self._settings["last_file"] = str(self._current_file)
            self._save_settings()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file:\n{e}")

    def _handle_unsaved_changes(self) -> bool:
        """Prompt user to save/discard/cancel unsaved changes.

        Returns True if the caller should proceed with its action
        (changes were saved or discarded), False to abort.
        """
        dialog = _UnsavedChangesDialog(self)
        choice = dialog.result

        if choice == "save":
            self._save()
            return not self._dirty  # False if save was cancelled
        elif choice == "save_as":
            self._save_as()
            return not self._dirty
        elif choice == "discard":
            return True
        else:  # cancel
            return False

    def _on_close(self):
        if self._dirty:
            if not self._handle_unsaved_changes():
                return
        self._settings["geometry"] = self.geometry()
        self._save_settings()
        self.destroy()

    def _update_title(self):
        name = self._current_file.name if self._current_file else "Untitled"
        dirty = " *" if self._dirty else ""
        self.title(f"FRC Controller Config - {name}{dirty}")

    def _mark_dirty(self):
        self._dirty = True
        self._update_title()
        self._action_panel.update_binding_tags()

    # --- Undo / Redo ---

    _UNDO_LIMIT = 50

    def _take_snapshot(self) -> tuple[FullConfig, set[str]]:
        """Capture current config + action panel empty groups."""
        self._sync_config_from_ui()
        return (deepcopy(self._config),
                self._action_panel.get_empty_groups())

    def _push_undo(self, coalesce_ms: int = 0):
        """Snapshot current state onto the undo stack.

        Args:
            coalesce_ms: if > 0 and the last push was within this many ms,
                replace the top of the stack instead of pushing a new entry.
                Useful for coalescing rapid keystrokes in text fields.
        """
        now = time.monotonic()
        if coalesce_ms and self._undo_stack:
            if (now - self._last_undo_time) < (coalesce_ms / 1000.0):
                self._undo_stack[-1] = self._take_snapshot()
                self._redo_stack.clear()
                return
        self._undo_stack.append(self._take_snapshot())
        if len(self._undo_stack) > self._UNDO_LIMIT:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._last_undo_time = now

    def _restore_snapshot(self, config: FullConfig, empty_groups: set[str]):
        """Restore a config snapshot and re-sync the UI."""
        self._restoring = True
        try:
            self._config = config
            # Merge legacy undo-stack empty_groups into config
            self._config.empty_groups = (
                self._config.empty_groups | empty_groups)
            self._sync_ui_from_config()
        finally:
            self._restoring = False

    def _undo(self):
        """Undo the last change."""
        if not self._undo_stack:
            self._status_var.set("Nothing to undo")
            return
        self._redo_stack.append(self._take_snapshot())
        config, empty_groups = self._undo_stack.pop()
        self._restore_snapshot(config, empty_groups)
        self._dirty = bool(self._undo_stack)
        self._update_title()
        self._status_var.set("Undo")

    def _redo(self):
        """Redo the last undone change."""
        if not self._redo_stack:
            self._status_var.set("Nothing to redo")
            return
        self._undo_stack.append(self._take_snapshot())
        config, empty_groups = self._redo_stack.pop()
        self._restore_snapshot(config, empty_groups)
        self._dirty = True
        self._update_title()
        self._status_var.set("Redo")

    # --- UI <-> Config Sync ---

    def _sync_ui_from_config(self):
        """Push config data to all UI elements."""
        # Update action panel
        self._action_panel.set_actions(self._config.actions)
        self._action_panel.set_empty_groups(self._config.empty_groups)

        # Update controller tabs — reuse existing canvases when possible
        new_ports = sorted(self._config.controllers.keys())
        old_ports = sorted(self._controller_canvases.keys())

        if new_ports == old_ports:
            # Same controllers — just update bindings and tab labels in place
            for idx, port in enumerate(new_ports):
                ctrl = self._config.controllers[port]
                self._controller_canvases[port].set_bindings(ctrl.bindings)
                label = ctrl.name or f"Controller {port}"
                self._notebook.tab(idx, text=f"{label} (Port {port})")
        else:
            # Controller set changed — full rebuild
            for tab_id in self._notebook.tabs():
                self._notebook.forget(tab_id)
            self._controller_canvases.clear()
            for port in new_ports:
                ctrl = self._config.controllers[port]
                self._create_controller_tab(port, ctrl)

    def _sync_config_from_ui(self):
        """Pull current UI state back into the config."""
        self._config.actions = self._action_panel.get_actions()
        self._config.empty_groups = self._action_panel.get_empty_groups()

    def _create_controller_tab(self, port: int, ctrl: ControllerConfig):
        """Create a tab for a controller."""
        tab_frame = ttk.Frame(self._notebook)
        label = ctrl.name or f"Controller {port}"
        self._notebook.add(tab_frame, text=f"{label} (Port {port})")

        # Name editor at top of tab
        name_frame = ttk.Frame(tab_frame)
        name_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(name_frame, text="Controller Name:").pack(side=tk.LEFT)
        name_var = tk.StringVar(value=ctrl.name)
        name_entry = ttk.Entry(name_frame, textvariable=name_var, width=20)
        name_entry.pack(side=tk.LEFT, padx=5)

        def on_name_change(*args, p=port, v=name_var):
            if self._restoring:
                return
            if p in self._config.controllers:
                self._push_undo(coalesce_ms=500)
                self._config.controllers[p].name = v.get()
                # Update tab label
                idx = sorted(self._config.controllers.keys()).index(p)
                label_text = v.get() or f"Controller {p}"
                self._notebook.tab(idx, text=f"{label_text} (Port {p})")
                self._mark_dirty()

        name_var.trace_add("write", on_name_change)

        # Controller canvas
        canvas = ControllerCanvas(
            tab_frame,
            on_binding_click=lambda input_name, p=port: self._on_binding_click(p, input_name),
            on_binding_clear=lambda input_name, p=port: self._on_binding_clear(p, input_name),
            on_mouse_coord=self._on_mouse_coord,
            on_label_moved=self._on_label_moved,
            on_hover_input=lambda input_name, p=port: self._on_hover_input(p, input_name),
            on_hover_shape=lambda input_names, p=port: self._on_hover_shape(p, input_names),
            on_action_remove=lambda input_name, action, p=port: self._on_action_remove(p, input_name, action),
            label_positions=self._settings.get("label_positions", {}),
        )
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.set_bindings(ctrl.bindings)
        canvas.set_show_borders(self._show_borders_var.get())
        canvas.set_labels_locked(self._lock_labels_var.get())
        canvas.set_hide_unassigned(self._hide_unassigned_var.get())

        self._controller_canvases[port] = canvas

    def _add_controller_tab(self):
        """Add a new controller at the next available port."""
        self._push_undo()
        existing_ports = set(self._config.controllers.keys())
        port = 0
        while port in existing_ports:
            port += 1

        ctrl = ControllerConfig(port=port, name=f"Controller {port}")
        self._config.controllers[port] = ctrl
        self._create_controller_tab(port, ctrl)
        self._mark_dirty()

        # Select the new tab
        self._notebook.select(len(self._notebook.tabs()) - 1)

    def _remove_controller_tab(self):
        """Remove the currently selected controller tab."""
        current = self._notebook.index(self._notebook.select())
        ports = sorted(self._config.controllers.keys())
        if current >= len(ports):
            return
        port = ports[current]

        if not messagebox.askyesno("Remove Controller",
                                   f"Remove controller on port {port}?"):
            return

        self._push_undo()
        del self._config.controllers[port]
        if port in self._controller_canvases:
            del self._controller_canvases[port]
        self._notebook.forget(current)
        self._mark_dirty()

    # --- Callbacks ---

    def _on_mouse_coord(self, img_x: int, img_y: int):
        """Update status bar with mouse position in source image pixels."""
        # Don't overwrite action info while hovering a binding box
        if not self._hover_status_active:
            self._status_var.set(f"Image coords: ({img_x}, {img_y})")

    def _format_action_status(self, port: int, input_names: list[str]) -> str | None:
        """Build a status string for actions bound to the given inputs."""
        ctrl = self._config.controllers.get(port)
        if not ctrl:
            return None

        parts = []
        for input_name in input_names:
            for action_name in ctrl.bindings.get(input_name, []):
                action = self._config.actions.get(action_name)
                if action:
                    desc = action.description or "No description"
                    atype = action.input_type.value.capitalize()
                    parts.append(f"{action.qualified_name} ({atype}) - {desc}")
                else:
                    parts.append(action_name)
        return "  |  ".join(parts) if parts else None

    def _on_hover_input(self, port: int, input_name: str | None):
        """Update status bar with action info when hovering a binding box."""
        if not input_name:
            self._hover_status_active = False
            self._status_var.set("Ready")
            return

        text = self._format_action_status(port, [input_name])
        if text:
            self._hover_status_active = True
            self._status_var.set(text)
        else:
            self._hover_status_active = False

    def _on_hover_shape(self, port: int, input_names: list[str] | None):
        """Update status bar with action info when hovering a controller shape."""
        if not input_names:
            self._hover_status_active = False
            self._status_var.set("Ready")
            return

        text = self._format_action_status(port, input_names)
        if text:
            self._hover_status_active = True
            self._status_var.set(text)
        else:
            self._hover_status_active = False

    def _toggle_borders(self):
        """Toggle shape border visibility on all canvases."""
        show = self._show_borders_var.get()
        for canvas in self._controller_canvases.values():
            canvas.set_show_borders(show)
        self._settings["show_borders"] = show
        self._save_settings()

    def _toggle_lock_labels(self):
        """Toggle label dragging lock on all canvases."""
        locked = self._lock_labels_var.get()
        for canvas in self._controller_canvases.values():
            canvas.set_labels_locked(locked)
        self._status_var.set(
            "Label positions locked" if locked else "Label positions unlocked")

    def _toggle_hide_unassigned(self):
        """Toggle hiding of unassigned inputs on all canvases."""
        hide = self._hide_unassigned_var.get()
        for canvas in self._controller_canvases.values():
            canvas.set_hide_unassigned(hide)
        self._status_var.set(
            "Unassigned inputs hidden" if hide
            else "Unassigned inputs shown")

    def _reset_label_positions(self):
        """Reset all dragged label positions to defaults."""
        self._settings.pop("label_positions", None)
        self._save_settings()
        for canvas in self._controller_canvases.values():
            canvas.reset_label_positions()
        self._status_var.set("Label positions reset to defaults")

    def _on_label_moved(self, input_name: str, img_x: int, img_y: int):
        """Persist a dragged label position to settings."""
        positions = self._settings.setdefault("label_positions", {})
        positions[input_name] = [img_x, img_y]
        self._save_settings()

    # --- Drag-and-Drop (action panel → controller canvas) ---

    def _on_drag_start(self, action_qname: str):
        """Called when an action drag begins from the action panel."""
        self._drag_action = action_qname
        self._status_var.set(f"Dragging: {action_qname}")
        self.config(cursor="plus")
        for c in self._controller_canvases.values():
            c.set_drag_cursor(True)
        # Temporarily show all inputs so user can see all drop targets
        if self._hide_unassigned_var.get():
            for c in self._controller_canvases.values():
                c.set_hide_unassigned(False)
        # Grey out incompatible inputs
        compatible = self._get_compatible_inputs(action_qname)
        for c in self._controller_canvases.values():
            c.dim_incompatible_inputs(compatible)
        # Bind global handlers to track drag across widgets
        self.bind_all("<B1-Motion>", self._on_drag_motion, add="+")
        self.bind_all("<ButtonRelease-1>", self._on_drag_release, add="+")

    def _on_drag_end(self):
        """Called when the tree releases the mouse (safety cleanup)."""
        self._drag_cleanup()

    def _on_drag_motion(self, event):
        """Track drag across widgets, highlighting drop targets."""
        if not self._drag_action:
            return

        canvas = self._find_canvas_at(event.x_root, event.y_root)

        # Clear highlights on all canvases except the one under cursor
        for c in self._controller_canvases.values():
            if c is not canvas:
                c.clear_drop_highlight()

        if canvas:
            input_name = canvas.highlight_drop_target(
                event.x_root, event.y_root)
            if input_name:
                inp = XBOX_INPUT_MAP.get(input_name)
                display = inp.display_name if inp else input_name
                self._status_var.set(
                    f"Drop to bind: {self._drag_action} \u2192 {display}")
            else:
                self._status_var.set(f"Dragging: {self._drag_action}")
        else:
            self._status_var.set(f"Dragging: {self._drag_action}")

    def _on_drag_release(self, event):
        """Handle drop onto controller canvas."""
        action = self._drag_action
        if not action:
            self._drag_cleanup()
            return

        canvas = self._find_canvas_at(event.x_root, event.y_root)
        port = self._port_for_canvas(canvas) if canvas else None

        if canvas and port is not None:
            input_name, shape = canvas.get_drop_target(
                event.x_root, event.y_root)

            if input_name:
                self._bind_dropped_action(port, input_name, action)
            elif shape:
                # Multi-input shape: show picker menu
                self._show_drop_input_menu(
                    event, port, shape, action)
                # Full cleanup after menu closes (selection or dismiss)
                self._drag_cleanup()
                return

        self._drag_cleanup()

    def _check_type_compatible(self, action_qname: str,
                               input_name: str) -> bool:
        """Check if an action's type is compatible with a controller input.

        Shows a warning messagebox if incompatible.
        Returns True if compatible, False otherwise.
        """
        action_def = self._config.actions.get(action_qname)
        inp = XBOX_INPUT_MAP.get(input_name)
        if not action_def or not inp:
            return True  # Can't validate, allow it

        allowed = _COMPAT_ACTION_TYPES.get(inp.input_type)
        if allowed is None:
            return True  # Unknown input type, allow it

        if action_def.input_type in allowed:
            return True

        # Type mismatch — show warning popup
        action_type = action_def.input_type.value.capitalize()
        hint = _INPUT_TYPE_DESCRIPTION.get(inp.input_type, "")
        messagebox.showwarning(
            "Type Mismatch",
            f"Cannot bind '{action_qname}' ({action_type}) "
            f"to '{inp.display_name}' ({inp.input_type}).\n\n"
            f"{hint}.",
        )
        return False

    def _get_compatible_actions(self, input_name: str) -> list[str]:
        """Return action qualified names compatible with the given input."""
        inp = XBOX_INPUT_MAP.get(input_name)
        if not inp:
            return list(self._config.actions.keys())

        allowed = _COMPAT_ACTION_TYPES.get(inp.input_type)
        if allowed is None:
            return list(self._config.actions.keys())

        return [
            qname for qname, action_def in self._config.actions.items()
            if action_def.input_type in allowed
        ]

    def _get_compatible_inputs(self, action_qname: str) -> set[str]:
        """Return the set of input names compatible with the given action."""
        action_def = self._config.actions.get(action_qname)
        if not action_def:
            return {inp.name for inp in XBOX_INPUT_MAP.values()}
        compatible = set()
        for inp in XBOX_INPUT_MAP.values():
            allowed = _COMPAT_ACTION_TYPES.get(inp.input_type)
            if allowed is None or action_def.input_type in allowed:
                compatible.add(inp.name)
        return compatible

    def _get_binding_info_for_action(self, qname: str) -> list[tuple[str, str]]:
        """Return list of (controller_name, input_display) for an action.

        Used by ActionPanel for tooltips and color-coding.
        """
        result = []
        for port, ctrl in self._config.controllers.items():
            ctrl_label = ctrl.name or f"Controller {port}"
            for input_name, actions in ctrl.bindings.items():
                if qname in actions:
                    inp = XBOX_INPUT_MAP.get(input_name)
                    display = inp.display_name if inp else input_name
                    result.append((ctrl_label, display))
        return result

    def _get_all_controllers(self) -> list[tuple[int, str]]:
        """Return list of (port, controller_name) for the context menu."""
        return [
            (port, ctrl.name or f"Controller {port}")
            for port, ctrl in sorted(self._config.controllers.items())
        ]

    def _get_compatible_inputs_with_display(
            self, qname: str) -> list[tuple[str, str]]:
        """Return list of (input_name, display_name) compatible with action."""
        compatible_names = self._get_compatible_inputs(qname)
        result = []
        for inp in XBOX_INPUT_MAP.values():
            if inp.name in compatible_names:
                result.append((inp.name, inp.display_name))
        return result

    def _is_action_bound_to(self, qname: str, port: int,
                            input_name: str) -> bool:
        """Check if action is bound to a specific input on a controller."""
        ctrl = self._config.controllers.get(port)
        if not ctrl:
            return False
        return qname in ctrl.bindings.get(input_name, [])

    def _context_assign_action(self, qname: str, port: int,
                               input_name: str):
        """Assign an action to an input from the context menu."""
        self._bind_dropped_action(port, input_name, qname)

    def _context_unassign_action(self, qname: str, port: int,
                                 input_name: str):
        """Unassign an action from an input via the context menu."""
        self._on_action_remove(port, input_name, qname)

    def _context_unassign_all(self, qname: str):
        """Remove an action from all inputs on all controllers."""
        self._push_undo()
        changed = False
        for port, ctrl in self._config.controllers.items():
            for input_name in list(ctrl.bindings.keys()):
                actions = ctrl.bindings[input_name]
                if qname in actions:
                    actions.remove(qname)
                    changed = True
                    if not actions:
                        del ctrl.bindings[input_name]
            canvas = self._controller_canvases.get(port)
            if canvas:
                canvas.set_bindings(ctrl.bindings)
        if changed:
            self._mark_dirty()
            self._status_var.set(f"Removed {qname} from all inputs")

    def _bind_dropped_action(self, port: int, input_name: str, action: str):
        """Add an action binding from a drag-and-drop, preventing duplicates."""
        ctrl = self._config.controllers.get(port)
        if not ctrl:
            return

        inp = XBOX_INPUT_MAP.get(input_name)
        display = inp.display_name if inp else input_name

        # Type compatibility check
        if not self._check_type_compatible(action, input_name):
            return

        current = ctrl.bindings.get(input_name, [])
        if action in current:
            self._status_var.set(
                f"{action} already bound to {display}")
            return

        self._push_undo()
        ctrl.bindings.setdefault(input_name, []).append(action)
        canvas = self._controller_canvases.get(port)
        if canvas:
            canvas.set_bindings(ctrl.bindings)
        self._mark_dirty()
        self._status_var.set(f"Bound {action} \u2192 {display}")

    def _show_drop_input_menu(self, event, port: int, shape, action: str):
        """Show menu to pick which input of a multi-input shape to bind to."""
        menu = tk.Menu(self, tearoff=0)
        for input_name in shape.inputs:
            inp = XBOX_INPUT_MAP.get(input_name)
            display = inp.display_name if inp else input_name
            menu.add_command(
                label=display,
                command=lambda n=input_name: self._bind_dropped_action(
                    port, n, action),
            )
        menu.tk_popup(event.x_root, event.y_root)

    def _find_canvas_at(self, x_root: int, y_root: int):
        """Find the ControllerCanvas widget under the given root coordinates."""
        widget = self.winfo_containing(x_root, y_root)
        while widget:
            if isinstance(widget, ControllerCanvas):
                return widget
            widget = getattr(widget, 'master', None)
        return None

    def _port_for_canvas(self, canvas: ControllerCanvas) -> int | None:
        """Return the port number for a given canvas widget."""
        for port, c in self._controller_canvases.items():
            if c is canvas:
                return port
        return None

    def _unbind_drag_handlers(self):
        """Remove global drag event handlers."""
        self.unbind_all("<B1-Motion>")
        self.unbind_all("<ButtonRelease-1>")

    def _drag_cleanup(self):
        """Reset all drag state."""
        self._drag_action = None
        self._unbind_drag_handlers()
        self.config(cursor="")
        for c in self._controller_canvases.values():
            c.set_drag_cursor(False)
        for c in self._controller_canvases.values():
            c.clear_drop_highlight()
            c.clear_dim_overlays()
        # Restore hide-unassigned state after drag
        if self._hide_unassigned_var.get():
            for c in self._controller_canvases.values():
                c.set_hide_unassigned(True)
        if not self._hover_status_active:
            self._status_var.set("Ready")

    def _on_before_action_change(self, coalesce_ms: int):
        """Called by ActionPanel BEFORE it mutates actions (for undo snapshot)."""
        if self._restoring:
            return
        self._push_undo(coalesce_ms=coalesce_ms)

    def _on_actions_changed(self):
        """Called when actions are added/removed/modified in the action panel."""
        if self._restoring:
            return
        self._config.actions = self._action_panel.get_actions()
        self._mark_dirty()
        self._check_orphan_bindings()

    def _check_orphan_bindings(self):
        """Detect and offer to remove bindings referencing deleted actions."""
        orphans = []
        for port, ctrl in self._config.controllers.items():
            ctrl_label = ctrl.name or f"Controller {port}"
            for input_name, actions in ctrl.bindings.items():
                for qname in actions:
                    if qname not in self._config.actions:
                        inp = XBOX_INPUT_MAP.get(input_name)
                        display = inp.display_name if inp else input_name
                        orphans.append((port, input_name, qname,
                                        ctrl_label, display))
        if not orphans:
            return

        lines = [f"  {o[3]} / {o[4]}: {o[2]}" for o in orphans]
        detail = "\n".join(lines)
        msg = (
            "The following bindings reference actions that no "
            f"longer exist:\n\n{detail}"
            "\n\nRemove these orphaned bindings?"
        )
        if messagebox.askyesno("Orphaned Bindings", msg, parent=self):
            for port, input_name, qname, _, _ in orphans:
                ctrl = self._config.controllers.get(port)
                if not ctrl:
                    continue
                actions = ctrl.bindings.get(input_name, [])
                if qname in actions:
                    actions.remove(qname)
                if not actions and input_name in ctrl.bindings:
                    del ctrl.bindings[input_name]
            # Refresh canvases
            for port, ctrl in self._config.controllers.items():
                canvas = self._controller_canvases.get(port)
                if canvas:
                    canvas.set_bindings(ctrl.bindings)
            self._status_var.set(
                f"Removed {len(orphans)} orphaned binding(s)")

    def _on_action_renamed(self, old_qname: str, new_qname: str):
        """Update all binding references when an action's qualified name changes."""
        for port, ctrl in self._config.controllers.items():
            changed = False
            for input_name, actions in ctrl.bindings.items():
                if old_qname in actions:
                    idx = actions.index(old_qname)
                    actions[idx] = new_qname
                    changed = True
            if changed:
                canvas = self._controller_canvases.get(port)
                if canvas:
                    canvas.set_bindings(ctrl.bindings)

    def _on_binding_clear(self, port: int, input_name: str):
        """Clear all bindings for a specific input."""
        ctrl = self._config.controllers.get(port)
        if not ctrl:
            return
        if input_name in ctrl.bindings:
            self._push_undo()
            del ctrl.bindings[input_name]
            canvas = self._controller_canvases.get(port)
            if canvas:
                canvas.set_bindings(ctrl.bindings)
            self._mark_dirty()

    def _on_action_remove(self, port: int, input_name: str, action: str):
        """Remove a single action from an input's bindings."""
        ctrl = self._config.controllers.get(port)
        if not ctrl:
            return
        actions = ctrl.bindings.get(input_name, [])
        if action in actions:
            self._push_undo()
            actions.remove(action)
            if not actions:
                del ctrl.bindings[input_name]
            canvas = self._controller_canvases.get(port)
            if canvas:
                canvas.set_bindings(ctrl.bindings)
            self._mark_dirty()
            self._status_var.set(f"Removed {action} from {input_name}")

    def _on_binding_click(self, port: int, input_name: str):
        """Open the binding dialog for a specific input on a specific controller."""
        ctrl = self._config.controllers.get(port)
        if not ctrl:
            return

        current_actions = ctrl.bindings.get(input_name, [])
        # Only show actions whose type is compatible with this input
        available_actions = self._get_compatible_actions(input_name)

        # Build description map for the dialog
        descriptions = {
            qname: act.description
            for qname, act in self._config.actions.items()
            if act.description
        }

        dialog = BindingDialog(self, input_name, current_actions,
                               available_actions, descriptions)
        result = dialog.get_result()

        canvas = self._controller_canvases.get(port)

        if result is not None:
            self._push_undo()
            if result:
                ctrl.bindings[input_name] = result
            elif input_name in ctrl.bindings:
                del ctrl.bindings[input_name]

            # Refresh the canvas
            if canvas:
                canvas.set_bindings(ctrl.bindings)
            self._mark_dirty()

        # Clear selection so line returns to default color
        if canvas:
            canvas.clear_selection()

    # --- Import / Export ---

    def _import_actions(self):
        """Import actions from another YAML file, merging with current config."""
        path = filedialog.askopenfilename(
            title="Import Actions From...",
            initialdir=self._get_initial_dir(),
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            imported = load_actions_from_file(Path(path))
        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to load file:\n{e}")
            return

        if not imported:
            messagebox.showinfo("Import", "No actions found in the selected file.")
            return

        current = self._action_panel.get_actions()

        # Separate conflicts from non-conflicts
        conflicts = {qname for qname in imported if qname in current}
        non_conflicts = {qname: action for qname, action in imported.items()
                         if qname not in conflicts}

        # Resolve conflicts via dialog
        resolved = {}
        if conflicts:
            dialog = ImportConflictDialog(self, conflicts, current, imported)
            result = dialog.get_result()
            if result is None:
                return  # User canceled
            resolved = result

        # Merge
        self._push_undo()
        merged = dict(current)
        merged.update(non_conflicts)
        merged.update(resolved)

        self._restoring = True  # Prevent _on_actions_changed from pushing
        self._action_panel.set_actions(merged)
        self._restoring = False
        self._config.actions = self._action_panel.get_actions()
        self._mark_dirty()

        count = len(non_conflicts) + len(resolved)
        self._status_var.set(
            f"Imported {count} action(s) from {Path(path).name}")

    def _export_group(self, group_name: str):
        """Export a single group's actions to a YAML file."""
        self._sync_config_from_ui()

        group_actions = {
            qname: action
            for qname, action in self._config.actions.items()
            if action.group == group_name
        }

        if not group_actions:
            messagebox.showinfo("Export", f"Group '{group_name}' has no actions.")
            return

        path = filedialog.asksaveasfilename(
            title=f"Export Group: {group_name}",
            initialdir=self._get_initial_dir(),
            initialfile=f"{group_name}.yaml",
            defaultextension=".yaml",
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            save_actions_to_file(group_actions, Path(path))
            self._status_var.set(
                f"Exported group '{group_name}' to {Path(path).name}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export:\n{e}")

    def _export_all_groups(self):
        """Export each group as a separate YAML file in a chosen directory."""
        self._sync_config_from_ui()

        if not self._config.actions:
            messagebox.showinfo("Export", "No actions to export.")
            return

        directory = filedialog.askdirectory(
            title="Export All Groups To...",
            initialdir=self._get_initial_dir(),
        )
        if not directory:
            return

        # Group actions by group name
        groups: dict[str, dict[str, object]] = {}
        for qname, action in self._config.actions.items():
            groups.setdefault(action.group, {})[qname] = action

        try:
            for group_name, group_actions in groups.items():
                out_path = Path(directory) / f"{group_name}.yaml"
                save_actions_to_file(group_actions, out_path)

            self._status_var.set(
                f"Exported {len(groups)} group(s) to {directory}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export:\n{e}")

    def _print_export(self, orientation: str, fmt: str):
        """Export controller layouts as PNG or PDF."""
        self._sync_config_from_ui()

        if not self._config.controllers:
            messagebox.showinfo("Export", "No controllers to export.")
            return

        ext = f".{fmt}"
        filetypes = (
            [("PNG files", "*.png"), ("All files", "*.*")] if fmt == "png"
            else [("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        path = filedialog.asksaveasfilename(
            title=f"Export {orientation.title()} {fmt.upper()}",
            initialdir=self._get_initial_dir(),
            initialfile=f"controllers_{orientation}{ext}",
            defaultextension=ext,
            filetypes=filetypes,
        )
        if not path:
            return

        try:
            label_positions = self._settings.get("label_positions", {})
            export_pages(self._config, orientation, Path(path),
                         label_positions,
                         self._hide_unassigned_var.get())
            self._status_var.set(
                f"Exported {orientation} {fmt.upper()} to {Path(path).name}")
        except Exception as e:
            messagebox.showerror("Export Error",
                                 f"Failed to export:\n{e}")

    def _export_assignments(self):
        """Export controller assignments (no actions) to a YAML file."""
        self._sync_config_from_ui()

        if not self._config.controllers:
            messagebox.showinfo("Export", "No controllers to export.")
            return

        path = filedialog.asksaveasfilename(
            title="Export Assignments",
            initialdir=self._get_initial_dir(),
            initialfile="assignments.yaml",
            defaultextension=".yaml",
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            save_assignments_to_file(self._config.controllers, Path(path))
            self._status_var.set(f"Exported assignments to {Path(path).name}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export:\n{e}")
