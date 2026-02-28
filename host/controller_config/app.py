"""Main application window for the controller configuration tool.

Ties together the action panel, controller canvas, and binding dialog
with a menu bar and controller tabs.
"""

import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

import sys
import os

# Ensure project root is on the path so utils.controller can be imported
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Default directory for file dialogs (data/ relative to repo root)
_default_data_dir = _project_root / "data"

# Settings file to remember last opened config
_settings_file = Path(__file__).resolve().parent / ".settings.json"

from utils.controller.model import FullConfig, ControllerConfig
from utils.controller.config_io import load_config, save_config

from .action_panel import ActionPanel
from .binding_dialog import BindingDialog
from .controller_canvas import ControllerCanvas


class ControllerConfigApp(tk.Tk):
    """Main application window."""

    def __init__(self, initial_file: str | None = None):
        super().__init__()
        self.title("FRC Controller Configuration")
        self.geometry("1200x700")
        self.minsize(900, 550)

        self._config = FullConfig()
        self._current_file: Path | None = None
        self._dirty = False
        self._settings = self._load_settings()

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
        file_menu.add_command(label="Exit", command=self._on_close)

        self.bind_all("<Control-n>", lambda e: self._new_config())
        self.bind_all("<Control-o>", lambda e: self._open_dialog())
        self.bind_all("<Control-s>", lambda e: self._save())
        self.bind_all("<Control-Shift-S>", lambda e: self._save_as())

    def _build_layout(self):
        # Main horizontal pane: action panel (left) | controller tabs (right)
        self._paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self._paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left: Action panel
        self._action_panel = ActionPanel(self._paned, on_actions_changed=self._on_actions_changed)
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
        self._status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self, textvariable=self._status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=2)

    # --- Settings Persistence ---

    @staticmethod
    def _load_settings() -> dict:
        """Load app settings (last opened file, etc.)."""
        try:
            if _settings_file.exists():
                return json.loads(_settings_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass
        return {}

    def _save_settings(self):
        """Persist app settings."""
        try:
            _settings_file.write_text(json.dumps(self._settings, indent=2))
        except OSError:
            pass

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
        if self._dirty and not self._confirm_discard():
            return

        self._config = FullConfig(
            controllers={
                0: ControllerConfig(port=0, name="Driver"),
                1: ControllerConfig(port=1, name="Operator"),
            }
        )
        self._current_file = None
        self._dirty = False
        self._sync_ui_from_config()
        self._update_title()
        self._status_var.set("New configuration created")

    def _open_dialog(self):
        if self._dirty and not self._confirm_discard():
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

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno(
            "Unsaved Changes",
            "You have unsaved changes. Discard them?",
        )

    def _on_close(self):
        if self._dirty:
            if not self._confirm_discard():
                return
        self.destroy()

    def _update_title(self):
        name = self._current_file.name if self._current_file else "Untitled"
        dirty = " *" if self._dirty else ""
        self.title(f"FRC Controller Config - {name}{dirty}")

    def _mark_dirty(self):
        self._dirty = True
        self._update_title()

    # --- UI <-> Config Sync ---

    def _sync_ui_from_config(self):
        """Push config data to all UI elements."""
        # Update action panel
        self._action_panel.set_actions(self._config.actions)

        # Rebuild controller tabs
        for tab_id in self._notebook.tabs():
            self._notebook.forget(tab_id)
        self._controller_canvases.clear()

        for port in sorted(self._config.controllers.keys()):
            ctrl = self._config.controllers[port]
            self._create_controller_tab(port, ctrl)

    def _sync_config_from_ui(self):
        """Pull current UI state back into the config."""
        self._config.actions = self._action_panel.get_actions()

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
            if p in self._config.controllers:
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
        )
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.set_bindings(ctrl.bindings)

        self._controller_canvases[port] = canvas

    def _add_controller_tab(self):
        """Add a new controller at the next available port."""
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

        del self._config.controllers[port]
        if port in self._controller_canvases:
            del self._controller_canvases[port]
        self._notebook.forget(current)
        self._mark_dirty()

    # --- Callbacks ---

    def _on_actions_changed(self):
        """Called when actions are added/removed/modified in the action panel."""
        self._config.actions = self._action_panel.get_actions()
        self._mark_dirty()

    def _on_binding_click(self, port: int, input_name: str):
        """Open the binding dialog for a specific input on a specific controller."""
        ctrl = self._config.controllers.get(port)
        if not ctrl:
            return

        current_actions = ctrl.bindings.get(input_name, [])
        available_actions = self._action_panel.get_action_names()

        dialog = BindingDialog(self, input_name, current_actions, available_actions)
        result = dialog.get_result()

        if result is not None:
            if result:
                ctrl.bindings[input_name] = result
            elif input_name in ctrl.bindings:
                del ctrl.bindings[input_name]

            # Refresh the canvas
            canvas = self._controller_canvases.get(port)
            if canvas:
                canvas.set_bindings(ctrl.bindings)
            self._mark_dirty()
