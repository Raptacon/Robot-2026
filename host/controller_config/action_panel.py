"""Action list and detail editor panel.

Left-side panel showing all defined actions organized in collapsible
groups with add/edit/delete capabilities.  When an action is selected,
its metadata is shown in an editable detail form below the tree.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from utils.controller.model import (
    ANALOG_TRIGGER_MODES,
    ActionDefinition,
    BUTTON_TRIGGER_MODES,
    InputType,
    TriggerMode,
)

# Tooltip delay in milliseconds (500ms balances responsiveness vs flicker)
_TOOLTIP_DELAY_MS = 500


class _WidgetTooltip:
    """Tooltip that appears after hovering over a widget for a delay."""

    def __init__(self, widget, text: str, delay: int = _TOOLTIP_DELAY_MS):
        self._widget = widget
        self.text = text
        self._delay = delay
        self._tip_window: tk.Toplevel | None = None
        self._after_id: str | None = None

        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)

    def _on_enter(self, event):
        self._schedule()

    def _on_leave(self, event):
        self._hide()

    def _schedule(self):
        self._hide()
        self._after_id = self._widget.after(self._delay, self._show)

    def _show(self):
        if not self.text:
            return
        self._tip_window = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)

        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 5
        tw.wm_geometry(f"+{x}+{y}")

        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID,
                         borderwidth=1, padx=4, pady=2,
                         font=("TkDefaultFont", 9))
        label.pack()

    def _hide(self):
        if self._after_id:
            self._widget.after_cancel(self._after_id)
            self._after_id = None
        if self._tip_window:
            self._tip_window.destroy()
            self._tip_window = None


class _TreeTooltip:
    """Tooltip that appears after hovering over a treeview item."""

    def __init__(self, tree: ttk.Treeview, delay: int = _TOOLTIP_DELAY_MS):
        self._tree = tree
        self._delay = delay
        self._tip_window: tk.Toplevel | None = None
        self._after_id: str | None = None
        self._current_item: str | None = None
        self._text_fn = None  # callable(item_id) -> str | None

        tree.bind("<Motion>", self._on_motion)
        tree.bind("<Leave>", self._on_leave)

    def set_text_fn(self, fn):
        """Set a callable(item_id) -> str|None that provides tooltip text."""
        self._text_fn = fn

    def _on_motion(self, event):
        item = self._tree.identify_row(event.y)
        if item != self._current_item:
            self._hide()
            self._current_item = item
            if item and self._text_fn:
                self._after_id = self._tree.after(
                    self._delay, lambda: self._show(item))

    def _on_leave(self, event):
        self._hide()
        self._current_item = None

    def _show(self, item: str):
        if self._current_item != item or not self._text_fn:
            return
        text = self._text_fn(item)
        if not text:
            return

        self._tip_window = tw = tk.Toplevel(self._tree)
        tw.wm_overrideredirect(True)

        x = self._tree.winfo_pointerx() + 15
        y = self._tree.winfo_pointery() + 10
        tw.wm_geometry(f"+{x}+{y}")

        label = tk.Label(tw, text=text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID,
                         borderwidth=1, padx=4, pady=2,
                         font=("TkDefaultFont", 9))
        label.pack()

    def _hide(self):
        if self._after_id:
            self._tree.after_cancel(self._after_id)
            self._after_id = None
        if self._tip_window:
            self._tip_window.destroy()
            self._tip_window = None


class ActionPanel(tk.Frame):
    """Panel for managing grouped action definitions."""

    # Treeview item-id prefix for group nodes
    _GROUP_PREFIX = "group::"

    # Drag threshold in pixels before drag-and-drop starts
    _DRAG_THRESHOLD = 5

    def __init__(self, parent, on_actions_changed=None, on_export_group=None,
                 on_drag_start=None, on_drag_end=None,
                 on_before_change=None):
        """
        Args:
            parent: tkinter parent widget
            on_actions_changed: callback() when any action is added/removed/modified
            on_export_group: callback(group_name) when user requests group export
            on_drag_start: callback(qname) when an action drag begins
            on_drag_end: callback() when a drag ends (release)
            on_before_change: callback(coalesce_ms) called BEFORE any mutation,
                giving the app a chance to snapshot state for undo
        """
        super().__init__(parent, padx=5, pady=5)
        self._on_actions_changed = on_actions_changed
        self._on_export_group = on_export_group
        self._on_before_change = on_before_change
        self._on_drag_start = on_drag_start
        self._on_drag_end = on_drag_end
        self._actions: dict[str, ActionDefinition] = {}
        self._empty_groups: set[str] = set()
        self._selected_name: str | None = None
        self._updating_form = False  # Guard against feedback loops

        # Drag-from-tree state
        self._drag_item: str | None = None
        self._drag_start_pos: tuple[int, int] = (0, 0)
        self._drag_started: bool = False

        self._build_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # --- Action Tree ---
        list_frame = ttk.LabelFrame(self, text="Actions", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True)

        tree_container = tk.Frame(list_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)

        self._tree = ttk.Treeview(tree_container, selectmode="browse", show="tree")
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # Drag-from-tree bindings
        self._tree.bind("<ButtonPress-1>", self._on_tree_press)
        self._tree.bind("<B1-Motion>", self._on_tree_drag)
        self._tree.bind("<ButtonRelease-1>", self._on_tree_release)

        tree_scroll = ttk.Scrollbar(tree_container, orient=tk.VERTICAL,
                                    command=self._tree.yview)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.configure(yscrollcommand=tree_scroll.set)

        # Tooltip for action descriptions
        self._tooltip = _TreeTooltip(self._tree)
        self._tooltip.set_text_fn(self._get_tooltip_text)

        # Right-click context menu
        self._context_menu = tk.Menu(self, tearoff=0)
        self._context_menu.add_command(label="Export Group...",
                                       command=self._on_context_export_group)
        self._tree.bind("<Button-3>", self._on_right_click)

        # Action buttons
        btn_frame = tk.Frame(list_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(btn_frame, text="Add", command=self._add_action,
                   width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Remove", command=self._remove_action,
                   width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Duplicate", command=self._duplicate_action,
                   width=8).pack(side=tk.LEFT, padx=2)

        # Group buttons
        group_btn_frame = tk.Frame(list_frame)
        group_btn_frame.pack(fill=tk.X, pady=(2, 0))
        ttk.Button(group_btn_frame, text="Add Group",
                   command=self._add_group, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(group_btn_frame, text="Remove Group",
                   command=self._remove_group, width=12).pack(side=tk.LEFT, padx=2)

        # --- Detail Editor ---
        self._detail_frame = ttk.LabelFrame(self, text="Action Details", padding=5)
        self._detail_frame.pack(fill=tk.X, pady=(10, 0))

        row = 0

        # Name
        self._name_label = ttk.Label(self._detail_frame, text="Name:")
        self._name_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._name_var = tk.StringVar()
        self._name_entry = ttk.Entry(self._detail_frame,
                                     textvariable=self._name_var, width=20)
        self._name_entry.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._name_var.trace_add("write", self._on_name_changed)

        # Group
        row += 1
        self._group_label = ttk.Label(self._detail_frame, text="Group:")
        self._group_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._group_var = tk.StringVar()
        self._group_combo = ttk.Combobox(self._detail_frame,
                                         textvariable=self._group_var, width=17)
        self._group_combo.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._group_var.trace_add("write", self._on_group_changed)

        # Description
        row += 1
        self._desc_label = ttk.Label(self._detail_frame, text="Description:")
        self._desc_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._desc_var = tk.StringVar()
        self._desc_entry = ttk.Entry(self._detail_frame,
                                     textvariable=self._desc_var, width=20)
        self._desc_entry.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._desc_var.trace_add("write", self._on_field_changed)

        # Input Type
        row += 1
        self._input_type_label = ttk.Label(self._detail_frame, text="Input Type:")
        self._input_type_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._input_type_var = tk.StringVar()
        self._input_type_combo = ttk.Combobox(
            self._detail_frame, textvariable=self._input_type_var,
            values=[t.value for t in InputType], state="readonly", width=17,
        )
        self._input_type_combo.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._input_type_var.trace_add("write", self._on_input_type_changed)

        # Trigger Mode
        row += 1
        self._trigger_label = ttk.Label(self._detail_frame, text="Trigger Mode:")
        self._trigger_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._trigger_var = tk.StringVar()
        self._trigger_combo = ttk.Combobox(
            self._detail_frame, textvariable=self._trigger_var,
            values=[t.value for t in BUTTON_TRIGGER_MODES],
            state="readonly", width=17,
        )
        self._trigger_combo.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._trigger_var.trace_add("write", self._on_field_changed)

        # Deadband (axis only)
        row += 1
        self._deadband_label = ttk.Label(self._detail_frame, text="Deadband:")
        self._deadband_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._deadband_var = tk.StringVar(value="0.0")
        self._deadband_spin = ttk.Spinbox(
            self._detail_frame, textvariable=self._deadband_var,
            from_=0.0, to=1.0, increment=0.01, width=17,
        )
        self._deadband_spin.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._deadband_var.trace_add("write", self._on_field_changed)

        # Inversion (axis only)
        row += 1
        self._inversion_label = ttk.Label(self._detail_frame, text="Inversion:")
        self._inversion_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._inversion_var = tk.BooleanVar()
        self._inversion_check = ttk.Checkbutton(
            self._detail_frame, variable=self._inversion_var,
        )
        self._inversion_check.grid(row=row, column=1, sticky=tk.W, pady=2)
        self._inversion_var.trace_add("write", self._on_field_changed)

        # Scale (axis only)
        row += 1
        self._scale_label = ttk.Label(self._detail_frame, text="Scale:")
        self._scale_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._scale_var = tk.StringVar(value="1.0")
        self._scale_spin = ttk.Spinbox(
            self._detail_frame, textvariable=self._scale_var,
            from_=-10.0, to=10.0, increment=0.1, width=17,
        )
        self._scale_spin.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._scale_var.trace_add("write", self._on_field_changed)

        self._detail_frame.columnconfigure(1, weight=1)

        # Analog-only widgets for show/hide
        self._axis_widgets = [
            (self._deadband_label, self._deadband_spin),
            (self._inversion_label, self._inversion_check),
            (self._scale_label, self._scale_spin),
        ]

        # Tooltips for detail form fields (label + widget share the same text)
        _name_tip = ("Short action name (no dots). Combined with\n"
                     "group to form qualified name: group.name")
        _group_tip = ("Group this action belongs to.\n"
                      "Type a new name to create a group.")
        _desc_tip = ("Human-readable description of what\n"
                     "this action does on the robot.")
        _input_tip = ("button: digital on/off input\n"
                      "analog: continuous value (stick, trigger)\n"
                      "pov: D-pad / hat switch\n"
                      "output: rumble or LED feedback")
        _trigger_tip = ("Button: when the command fires.\n"
                        "Analog: how the input value is shaped.")
        _deadband_tip = ("Ignore input values below this threshold.\n"
                         "Prevents drift from stick center (0.0-1.0).")
        _inversion_tip = ("Negate the input value.\n"
                          "Useful for reversing stick directions.")
        _scale_tip = ("Multiplier applied to the input value.\n"
                      "Use to limit max speed or amplify input.")

        _WidgetTooltip(self._name_label, _name_tip)
        _WidgetTooltip(self._name_entry, _name_tip)
        _WidgetTooltip(self._group_label, _group_tip)
        _WidgetTooltip(self._group_combo, _group_tip)
        _WidgetTooltip(self._desc_label, _desc_tip)
        _WidgetTooltip(self._desc_entry, _desc_tip)
        _WidgetTooltip(self._input_type_label, _input_tip)
        _WidgetTooltip(self._input_type_combo, _input_tip)
        self._trigger_tooltip = _WidgetTooltip(self._trigger_label, _trigger_tip)
        _WidgetTooltip(self._trigger_combo, _trigger_tip)
        _WidgetTooltip(self._deadband_label, _deadband_tip)
        _WidgetTooltip(self._deadband_spin, _deadband_tip)
        _WidgetTooltip(self._inversion_label, _inversion_tip)
        _WidgetTooltip(self._inversion_check, _inversion_tip)
        _WidgetTooltip(self._scale_label, _scale_tip)
        _WidgetTooltip(self._scale_spin, _scale_tip)

        self._set_detail_enabled(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_actions(self, actions: dict[str, ActionDefinition]):
        """Load a full set of actions (e.g., from file)."""
        self._actions = dict(actions)
        self._empty_groups = set()
        self._refresh_tree()
        self._selected_name = None
        self._set_detail_enabled(False)

    def get_actions(self) -> dict[str, ActionDefinition]:
        """Return the current actions dict keyed by qualified name."""
        return dict(self._actions)

    def get_action_names(self) -> list[str]:
        """Return sorted list of fully qualified action names."""
        return sorted(self._actions.keys())

    def get_empty_groups(self) -> set[str]:
        """Return a copy of the empty-group set (for undo snapshots)."""
        return set(self._empty_groups)

    def set_empty_groups(self, groups: set[str]):
        """Restore the empty-group set (for undo restore)."""
        self._empty_groups = set(groups)

    # ------------------------------------------------------------------
    # Tree Management
    # ------------------------------------------------------------------

    def _collect_groups(self) -> dict[str, list[str]]:
        """Collect group -> [qualified_name, ...] mapping."""
        groups: dict[str, list[str]] = {}
        for qname, action in self._actions.items():
            groups.setdefault(action.group, []).append(qname)
        for g in self._empty_groups:
            if g not in groups:
                groups[g] = []
        return groups

    def _sorted_group_names(self, groups: dict[str, list[str]]) -> list[str]:
        """Sort group names with 'general' first."""
        return sorted(groups.keys(), key=lambda g: (g != "general", g))

    def _refresh_tree(self):
        """Rebuild the treeview from the actions dict."""
        self._tree.delete(*self._tree.get_children())

        groups = self._collect_groups()
        sorted_groups = self._sorted_group_names(groups)

        for group in sorted_groups:
            group_iid = f"{self._GROUP_PREFIX}{group}"
            self._tree.insert("", tk.END, iid=group_iid,
                              text=f" {group}", open=True, tags=("group",))

            for qname in sorted(groups[group],
                                key=lambda q: q.split(".", 1)[-1]):
                action = self._actions[qname]
                self._tree.insert(group_iid, tk.END, iid=qname,
                                  text=f"  {action.name}", tags=("action",))

        # Update group combo values
        self._group_combo['values'] = sorted_groups

        # Style rows
        self._tree.tag_configure("group", font=("TkDefaultFont", 9, "bold"))
        self._tree.tag_configure("action", font=("TkDefaultFont", 9))

    # ------------------------------------------------------------------
    # Selection Handling
    # ------------------------------------------------------------------

    def _on_select(self, event):
        """Handle tree selection change."""
        sel = self._tree.selection()
        if not sel:
            self._selected_name = None
            self._set_detail_enabled(False)
            return

        item_id = sel[0]
        if item_id.startswith(self._GROUP_PREFIX):
            self._selected_name = None
            self._set_detail_enabled(False)
            return

        self._selected_name = item_id
        self._load_detail(item_id)
        self._set_detail_enabled(True)

    def _load_detail(self, qname: str):
        """Populate the detail form from an action."""
        action = self._actions.get(qname)
        if not action:
            return

        self._updating_form = True
        try:
            self._name_var.set(action.name)
            self._group_var.set(action.group)
            self._desc_var.set(action.description)
            self._input_type_var.set(action.input_type.value)
            self._update_trigger_mode_options(action.input_type)
            self._trigger_var.set(action.trigger_mode.value)
            self._deadband_var.set(str(action.deadband))
            self._inversion_var.set(action.inversion)
            self._scale_var.set(str(action.scale))
        finally:
            self._updating_form = False

        self._update_type_visibility()

    def _set_detail_enabled(self, enabled: bool):
        """Enable or disable the detail form."""
        state = "normal" if enabled else "disabled"
        readonly_state = "readonly" if enabled else "disabled"
        self._name_entry.config(state=state)
        self._group_combo.config(state=state)
        for child in self._detail_frame.winfo_children():
            if isinstance(child, (ttk.Entry, ttk.Spinbox)):
                child.config(state=state)
            elif isinstance(child, ttk.Combobox):
                child.config(state=readonly_state)
            elif isinstance(child, ttk.Checkbutton):
                child.config(state=state)
        # The group combo is editable (not readonly) so users can type new names
        if enabled:
            self._group_combo.config(state=state)

    def _update_trigger_mode_options(self, input_type: InputType):
        """Update the trigger mode dropdown to show modes for the current input type.

        Output actions have no trigger mode — the row is hidden instead.
        """
        if input_type == InputType.OUTPUT:
            # Hide trigger mode entirely for outputs
            self._trigger_label.grid_remove()
            self._trigger_combo.grid_remove()
            return

        # Ensure trigger row is visible
        self._trigger_label.grid()
        self._trigger_combo.grid()

        if input_type == InputType.ANALOG:
            modes = ANALOG_TRIGGER_MODES
            default = TriggerMode.SCALED
        else:
            modes = BUTTON_TRIGGER_MODES
            default = TriggerMode.ON_TRUE

        values = [m.value for m in modes]
        self._trigger_combo['values'] = values

        # If current selection isn't valid for the new type, reset to default
        if self._trigger_var.get() not in values:
            self._trigger_var.set(default.value)

    def _update_type_visibility(self):
        """Show/hide fields based on input type.

        Analog-specific fields (deadband, inversion, scale) only shown for analog.
        Trigger mode hidden for output actions.
        """
        input_type_str = self._input_type_var.get()
        is_analog = input_type_str == InputType.ANALOG.value
        for label, widget in self._axis_widgets:
            if is_analog:
                label.grid()
                widget.grid()
            else:
                label.grid_remove()
                widget.grid_remove()

    # ------------------------------------------------------------------
    # Detail Form Changes
    # ------------------------------------------------------------------

    def _save_detail(self):
        """Save the detail form back to the action. Returns True if saved."""
        if self._updating_form or self._selected_name is None:
            return False

        action = self._actions.get(self._selected_name)
        if not action:
            return False

        try:
            action.description = self._desc_var.get()
            action.input_type = InputType(self._input_type_var.get())
            if action.input_type == InputType.OUTPUT:
                action.trigger_mode = TriggerMode.RAW
            else:
                action.trigger_mode = TriggerMode(self._trigger_var.get())
            action.deadband = float(self._deadband_var.get() or 0)
            action.inversion = self._inversion_var.get()
            action.scale = float(self._scale_var.get() or 1.0)
        except (ValueError, KeyError):
            return False

        return True

    def _on_field_changed(self, *args):
        """Handle changes to detail fields (not name or group)."""
        if self._updating_form:
            return
        if self._on_before_change:
            self._on_before_change(500)
        if self._save_detail() and self._on_actions_changed:
            self._on_actions_changed()

    def _on_input_type_changed(self, *args):
        """Handle input type dropdown change."""
        if not self._updating_form:
            try:
                input_type = InputType(self._input_type_var.get())
            except ValueError:
                input_type = InputType.BUTTON
            # Suppress intermediate traces from deadband/trigger var changes
            # so the final _on_field_changed captures a single pre-mutation snapshot
            self._updating_form = True
            try:
                if input_type == InputType.ANALOG:
                    # Default deadband to 5% when switching to analog
                    try:
                        current_db = float(self._deadband_var.get() or 0)
                    except ValueError:
                        current_db = 0.0
                    if current_db == 0.0:
                        self._deadband_var.set("0.05")
                # Update trigger mode options and default
                self._update_trigger_mode_options(input_type)
            finally:
                self._updating_form = False
        self._update_type_visibility()
        self._on_field_changed()

    def _on_name_changed(self, *args):
        """Handle renaming an action (short name)."""
        if self._updating_form or self._selected_name is None:
            return

        new_name = self._name_var.get().strip()
        old_qname = self._selected_name
        action = self._actions.get(old_qname)
        if not action or not new_name or new_name == action.name:
            return

        # Reject dots in short names
        if '.' in new_name:
            return

        new_qname = f"{action.group}.{new_name}"
        if new_qname in self._actions and new_qname != old_qname:
            return  # Duplicate

        if self._on_before_change:
            self._on_before_change(500)
        del self._actions[old_qname]
        action.name = new_name
        self._actions[new_qname] = action
        self._selected_name = new_qname

        self._refresh_tree()
        self._reselect(new_qname)

        if self._on_actions_changed:
            self._on_actions_changed()

    def _on_group_changed(self, *args):
        """Handle changing an action's group via the combo box."""
        if self._updating_form or self._selected_name is None:
            return

        new_group = self._group_var.get().strip()
        if not new_group:
            return

        action = self._actions.get(self._selected_name)
        if not action or new_group == action.group:
            return

        if self._on_before_change:
            self._on_before_change(0)
        old_qname = self._selected_name
        del self._actions[old_qname]

        action.group = new_group
        new_qname = action.qualified_name

        # Handle name collision in new group
        if new_qname in self._actions:
            base = action.name
            i = 1
            while f"{new_group}.{base}_{i}" in self._actions:
                i += 1
            action.name = f"{base}_{i}"
            new_qname = action.qualified_name

        self._actions[new_qname] = action
        self._selected_name = new_qname

        # Remove old group from empty tracking if it now has actions, or add it
        self._empty_groups.discard(new_group)

        self._refresh_tree()
        self._reselect(new_qname)

        if self._on_actions_changed:
            self._on_actions_changed()

    # ------------------------------------------------------------------
    # Action CRUD
    # ------------------------------------------------------------------

    def _add_action(self):
        """Add a new action in the currently selected group, or 'general'."""
        if self._on_before_change:
            self._on_before_change(0)
        group = self._get_selected_group()

        base = "new_action"
        name = base
        i = 1
        while f"{group}.{name}" in self._actions:
            name = f"{base}_{i}"
            i += 1

        qname = f"{group}.{name}"
        action = ActionDefinition(name=name, group=group)
        self._actions[qname] = action
        self._empty_groups.discard(group)
        self._refresh_tree()
        self._reselect(qname)

        self._selected_name = qname
        self._load_detail(qname)
        self._set_detail_enabled(True)

        self._name_entry.focus_set()
        self._name_entry.select_range(0, tk.END)

        if self._on_actions_changed:
            self._on_actions_changed()

    def _remove_action(self):
        """Remove the selected action."""
        if self._selected_name is None:
            return

        name = self._selected_name
        action = self._actions.get(name)
        display = action.qualified_name if action else name
        if not messagebox.askyesno("Remove Action",
                                   f"Remove action '{display}'?"):
            return

        if self._on_before_change:
            self._on_before_change(0)
        del self._actions[name]
        self._selected_name = None
        self._refresh_tree()
        self._set_detail_enabled(False)

        if self._on_actions_changed:
            self._on_actions_changed()

    def _duplicate_action(self):
        """Duplicate the selected action with a new name."""
        if self._selected_name is None:
            return

        if self._on_before_change:
            self._on_before_change(0)
        src = self._actions[self._selected_name]
        base = f"{src.name}_copy"
        name = base
        i = 1
        while f"{src.group}.{name}" in self._actions:
            name = f"{base}_{i}"
            i += 1

        new_action = ActionDefinition(
            name=name,
            description=src.description,
            group=src.group,
            input_type=src.input_type,
            trigger_mode=src.trigger_mode,
            deadband=src.deadband,
            inversion=src.inversion,
            scale=src.scale,
            extra=dict(src.extra),
        )
        qname = new_action.qualified_name
        self._actions[qname] = new_action
        self._refresh_tree()
        self._reselect(qname)

        self._selected_name = qname
        self._load_detail(qname)
        self._set_detail_enabled(True)

        if self._on_actions_changed:
            self._on_actions_changed()

    # ------------------------------------------------------------------
    # Group Management
    # ------------------------------------------------------------------

    def _add_group(self):
        """Prompt for a new group name and create an empty group node."""
        name = simpledialog.askstring("New Group", "Group name:", parent=self)
        if not name or not name.strip():
            return
        name = name.strip().lower().replace(" ", "_")

        # Check if group already exists
        groups = self._collect_groups()
        if name in groups:
            messagebox.showinfo("Group Exists",
                                f"Group '{name}' already exists.")
            return

        self._empty_groups.add(name)
        self._refresh_tree()

    def _remove_group(self):
        """Remove the selected group and all its actions."""
        group = self._get_selected_group_name()
        if not group:
            messagebox.showinfo("No Group Selected",
                                "Select a group to remove.")
            return

        group_actions = [qn for qn, a in self._actions.items()
                         if a.group == group]

        if group_actions:
            if not messagebox.askyesno(
                "Remove Group",
                f"Remove group '{group}' and its "
                f"{len(group_actions)} action(s)?",
            ):
                return
            if self._on_before_change:
                self._on_before_change(0)
            for qn in group_actions:
                del self._actions[qn]
        else:
            if self._on_before_change:
                self._on_before_change(0)
            self._empty_groups.discard(group)

        self._selected_name = None
        self._refresh_tree()
        self._set_detail_enabled(False)

        if self._on_actions_changed:
            self._on_actions_changed()

    # ------------------------------------------------------------------
    # Context Menu (Right-Click)
    # ------------------------------------------------------------------

    def _on_right_click(self, event):
        """Show context menu on right-click over a group node."""
        item = self._tree.identify_row(event.y)
        if item and item.startswith(self._GROUP_PREFIX):
            self._tree.selection_set(item)
            self._context_menu.post(event.x_root, event.y_root)

    def _on_context_export_group(self):
        """Handle 'Export Group...' from context menu."""
        group = self._get_selected_group_name()
        if group and self._on_export_group:
            self._on_export_group(group)

    # ------------------------------------------------------------------
    # Drag-from-Tree (cross-widget drag-and-drop)
    # ------------------------------------------------------------------

    def _on_tree_press(self, event):
        """Record potential drag start position."""
        item = self._tree.identify_row(event.y)
        if item and not item.startswith(self._GROUP_PREFIX) and item in self._actions:
            self._drag_item = item
            self._drag_start_pos = (event.x_root, event.y_root)
            self._drag_started = False
        else:
            self._drag_item = None

    def _on_tree_drag(self, event):
        """Start drag after movement exceeds threshold."""
        if not self._drag_item:
            return
        if self._drag_started:
            return  # Already notified app

        dx = event.x_root - self._drag_start_pos[0]
        dy = event.y_root - self._drag_start_pos[1]
        if (dx * dx + dy * dy) >= self._DRAG_THRESHOLD ** 2:
            self._drag_started = True
            if self._on_drag_start:
                self._on_drag_start(self._drag_item)

    def _on_tree_release(self, event):
        """Reset local drag state. Drop is handled by app's global handler."""
        self._drag_item = None
        self._drag_started = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_selected_group(self) -> str:
        """Return the group for the current selection, defaulting to 'general'."""
        sel = self._tree.selection()
        if sel:
            item_id = sel[0]
            if item_id.startswith(self._GROUP_PREFIX):
                return item_id[len(self._GROUP_PREFIX):]
            if item_id in self._actions:
                return self._actions[item_id].group
        return "general"

    def _get_selected_group_name(self) -> str | None:
        """Return the group name if a group node is selected, else None."""
        sel = self._tree.selection()
        if sel:
            item_id = sel[0]
            if item_id.startswith(self._GROUP_PREFIX):
                return item_id[len(self._GROUP_PREFIX):]
            # Also allow removing a group when an action in it is selected
            if item_id in self._actions:
                return self._actions[item_id].group
        return None

    def _get_tooltip_text(self, item_id: str) -> str | None:
        """Return tooltip text for a tree item, or None."""
        if item_id.startswith(self._GROUP_PREFIX):
            group = item_id[len(self._GROUP_PREFIX):]
            count = sum(1 for a in self._actions.values() if a.group == group)
            return f"{group} ({count} action{'s' if count != 1 else ''})"

        action = self._actions.get(item_id)
        if action and action.description:
            return f"{action.qualified_name}\n{action.description}"
        return None

    def _reselect(self, qname: str):
        """Select and scroll to an item in the tree."""
        if self._tree.exists(qname):
            self._tree.selection_set(qname)
            self._tree.see(qname)
