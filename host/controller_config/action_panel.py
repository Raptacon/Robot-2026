"""Action list and detail editor panel.

Left-side panel showing all defined actions with add/edit/delete
capabilities. When an action is selected, its metadata is shown
in an editable detail form below the list.
"""

import tkinter as tk
from tkinter import ttk, messagebox

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from utils.controller.model import ActionDefinition, InputType, TriggerMode


class ActionPanel(tk.Frame):
    """Panel for managing action definitions."""

    def __init__(self, parent, on_actions_changed=None):
        """
        Args:
            parent: tkinter parent widget
            on_actions_changed: callback() when any action is added/removed/modified
        """
        super().__init__(parent, padx=5, pady=5)
        self._on_actions_changed = on_actions_changed
        self._actions: dict[str, ActionDefinition] = {}
        self._selected_name: str | None = None
        self._updating_form = False  # Guard against feedback loops

        self._build_ui()

    def _build_ui(self):
        # --- Action List ---
        list_frame = ttk.LabelFrame(self, text="Actions", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True)

        self._listbox = tk.Listbox(list_frame, width=25, exportselection=False)
        self._listbox.pack(fill=tk.BOTH, expand=True)
        self._listbox.bind("<<ListboxSelect>>", self._on_select)

        btn_frame = tk.Frame(list_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(btn_frame, text="Add", command=self._add_action, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Remove", command=self._remove_action, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Duplicate", command=self._duplicate_action, width=8).pack(side=tk.LEFT, padx=2)

        # --- Detail Editor ---
        self._detail_frame = ttk.LabelFrame(self, text="Action Details", padding=5)
        self._detail_frame.pack(fill=tk.X, pady=(10, 0))

        # Name
        row = 0
        ttk.Label(self._detail_frame, text="Name:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self._name_var = tk.StringVar()
        self._name_entry = ttk.Entry(self._detail_frame, textvariable=self._name_var, width=20)
        self._name_entry.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._name_var.trace_add("write", self._on_name_changed)

        # Description
        row += 1
        ttk.Label(self._detail_frame, text="Description:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self._desc_var = tk.StringVar()
        ttk.Entry(self._detail_frame, textvariable=self._desc_var, width=20).grid(
            row=row, column=1, sticky=tk.EW, pady=2)
        self._desc_var.trace_add("write", self._on_field_changed)

        # Input Type
        row += 1
        ttk.Label(self._detail_frame, text="Input Type:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self._input_type_var = tk.StringVar()
        self._input_type_combo = ttk.Combobox(
            self._detail_frame, textvariable=self._input_type_var,
            values=[t.value for t in InputType], state="readonly", width=17,
        )
        self._input_type_combo.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._input_type_var.trace_add("write", self._on_input_type_changed)

        # Trigger Mode
        row += 1
        ttk.Label(self._detail_frame, text="Trigger Mode:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self._trigger_var = tk.StringVar()
        self._trigger_combo = ttk.Combobox(
            self._detail_frame, textvariable=self._trigger_var,
            values=[t.value for t in TriggerMode], state="readonly", width=17,
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
        self._deadband_row = row

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
        self._inversion_row = row

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
        self._scale_row = row

        self._detail_frame.columnconfigure(1, weight=1)

        # Axis-only widgets for show/hide
        self._axis_widgets = [
            (self._deadband_label, self._deadband_spin),
            (self._inversion_label, self._inversion_check),
            (self._scale_label, self._scale_spin),
        ]

        self._set_detail_enabled(False)

    def set_actions(self, actions: dict[str, ActionDefinition]):
        """Load a full set of actions (e.g., from file)."""
        self._actions = dict(actions)
        self._refresh_list()
        self._selected_name = None
        self._set_detail_enabled(False)

    def get_actions(self) -> dict[str, ActionDefinition]:
        """Return the current actions dict."""
        return dict(self._actions)

    def get_action_names(self) -> list[str]:
        """Return sorted list of action names."""
        return sorted(self._actions.keys())

    def _refresh_list(self):
        """Rebuild the listbox from the actions dict."""
        self._listbox.delete(0, tk.END)
        for name in sorted(self._actions.keys()):
            self._listbox.insert(tk.END, name)

    def _on_select(self, event):
        """Handle listbox selection change."""
        sel = self._listbox.curselection()
        if not sel:
            self._selected_name = None
            self._set_detail_enabled(False)
            return

        name = self._listbox.get(sel[0])
        self._selected_name = name
        self._load_detail(name)
        self._set_detail_enabled(True)

    def _load_detail(self, name: str):
        """Populate the detail form from an action."""
        action = self._actions.get(name)
        if not action:
            return

        self._updating_form = True
        try:
            self._name_var.set(action.name)
            self._desc_var.set(action.description)
            self._input_type_var.set(action.input_type.value)
            self._trigger_var.set(action.trigger_mode.value)
            self._deadband_var.set(str(action.deadband))
            self._inversion_var.set(action.inversion)
            self._scale_var.set(str(action.scale))
        finally:
            self._updating_form = False

        self._update_axis_visibility()

    def _set_detail_enabled(self, enabled: bool):
        """Enable or disable the detail form."""
        state = "normal" if enabled else "disabled"
        readonly_state = "readonly" if enabled else "disabled"
        self._name_entry.config(state=state)
        for child in self._detail_frame.winfo_children():
            if isinstance(child, (ttk.Entry, ttk.Spinbox)):
                child.config(state=state)
            elif isinstance(child, ttk.Combobox):
                child.config(state=readonly_state)
            elif isinstance(child, ttk.Checkbutton):
                child.config(state=state)

    def _update_axis_visibility(self):
        """Show/hide axis-specific fields based on input type."""
        is_axis = self._input_type_var.get() == InputType.AXIS.value
        for label, widget in self._axis_widgets:
            if is_axis:
                label.grid()
                widget.grid()
            else:
                label.grid_remove()
                widget.grid_remove()

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
            action.trigger_mode = TriggerMode(self._trigger_var.get())
            action.deadband = float(self._deadband_var.get() or 0)
            action.inversion = self._inversion_var.get()
            action.scale = float(self._scale_var.get() or 1.0)
        except (ValueError, KeyError):
            return False

        return True

    def _on_field_changed(self, *args):
        """Handle changes to detail fields (not name)."""
        if self._updating_form:
            return
        if self._save_detail() and self._on_actions_changed:
            self._on_actions_changed()

    def _on_input_type_changed(self, *args):
        """Handle input type dropdown change."""
        self._update_axis_visibility()
        self._on_field_changed()

    def _on_name_changed(self, *args):
        """Handle renaming an action."""
        if self._updating_form or self._selected_name is None:
            return

        new_name = self._name_var.get().strip()
        old_name = self._selected_name

        if not new_name or new_name == old_name:
            return

        # Check for duplicate names
        if new_name in self._actions and new_name != old_name:
            return

        # Rename the action
        action = self._actions.pop(old_name)
        action.name = new_name
        self._actions[new_name] = action
        self._selected_name = new_name

        self._refresh_list()

        # Re-select the renamed action
        names = sorted(self._actions.keys())
        if new_name in names:
            idx = names.index(new_name)
            self._listbox.selection_set(idx)
            self._listbox.see(idx)

        if self._on_actions_changed:
            self._on_actions_changed()

    def _add_action(self):
        """Add a new action with a unique default name."""
        base = "new_action"
        name = base
        i = 1
        while name in self._actions:
            name = f"{base}_{i}"
            i += 1

        action = ActionDefinition(name=name)
        self._actions[name] = action
        self._refresh_list()

        # Select the new action
        names = sorted(self._actions.keys())
        idx = names.index(name)
        self._listbox.selection_clear(0, tk.END)
        self._listbox.selection_set(idx)
        self._listbox.see(idx)
        self._selected_name = name
        self._load_detail(name)
        self._set_detail_enabled(True)

        # Focus the name field for immediate editing
        self._name_entry.focus_set()
        self._name_entry.select_range(0, tk.END)

        if self._on_actions_changed:
            self._on_actions_changed()

    def _remove_action(self):
        """Remove the selected action."""
        if self._selected_name is None:
            return

        name = self._selected_name
        if not messagebox.askyesno("Remove Action", f"Remove action '{name}'?"):
            return

        del self._actions[name]
        self._selected_name = None
        self._refresh_list()
        self._set_detail_enabled(False)

        if self._on_actions_changed:
            self._on_actions_changed()

    def _duplicate_action(self):
        """Duplicate the selected action with a new name."""
        if self._selected_name is None:
            return

        src = self._actions[self._selected_name]
        base = f"{src.name}_copy"
        name = base
        i = 1
        while name in self._actions:
            name = f"{base}_{i}"
            i += 1

        new_action = ActionDefinition(
            name=name,
            description=src.description,
            input_type=src.input_type,
            trigger_mode=src.trigger_mode,
            deadband=src.deadband,
            inversion=src.inversion,
            scale=src.scale,
            extra=dict(src.extra),
        )
        self._actions[name] = new_action
        self._refresh_list()

        # Select the duplicate
        names = sorted(self._actions.keys())
        idx = names.index(name)
        self._listbox.selection_clear(0, tk.END)
        self._listbox.selection_set(idx)
        self._listbox.see(idx)
        self._selected_name = name
        self._load_detail(name)
        self._set_detail_enabled(True)

        if self._on_actions_changed:
            self._on_actions_changed()
