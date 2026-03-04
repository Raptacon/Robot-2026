"""Action list and detail editor panel.

Left-side panel showing all defined actions organized in collapsible
groups with add/edit/delete capabilities.  When an action is selected,
its metadata is shown in an editable detail form below the tree.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import fnmatch
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from utils.controller.model import (
    ANALOG_EVENT_TRIGGER_MODES,
    ActionDefinition,
    BUTTON_EVENT_TRIGGER_MODES,
    InputType,
    EventTriggerMode,
)
from .tooltips import (
    TIP_NAME, TIP_GROUP, TIP_DESC, TIP_INPUT_TYPE,
    TIP_TRIGGER, TIP_DEADBAND, TIP_INVERSION, TIP_SCALE,
    TIP_SLEW, TIP_NEG_SLEW,
    TIP_EDIT_SPLINE, TIP_EDIT_SEGMENTS,
    TIP_FILTER, TIP_FILTER_UNASSIGNED, TIP_FILTER_MULTI,
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
    _DRAG_THRESHOLD = 8

    def __init__(self, parent, on_actions_changed=None, on_export_group=None,
                 on_drag_start=None, on_drag_end=None,
                 on_before_change=None, get_binding_info=None,
                 on_assign_action=None, on_unassign_action=None,
                 on_unassign_all=None, get_all_controllers=None,
                 get_compatible_inputs=None, is_action_bound=None,
                 on_action_renamed=None,
                 on_selection_changed=None):
        """
        Args:
            parent: tkinter parent widget
            on_actions_changed: callback() when any action is added/removed/modified
            on_export_group: callback(group_name) when user requests group export
            on_drag_start: callback(qname) when an action drag begins
            on_drag_end: callback() when a drag ends (release)
            on_before_change: callback(coalesce_ms) called BEFORE any mutation,
                giving the app a chance to snapshot state for undo
            get_binding_info: callback(qname) -> list[(ctrl_name, input_display)]
                returns where an action is bound, or empty list if unbound
            on_assign_action: callback(qname, port, input_name) to bind action
            on_unassign_action: callback(qname, port, input_name) to unbind action
            on_unassign_all: callback(qname) to remove action from all inputs
            get_all_controllers: callback() -> list[(port, ctrl_name)]
            get_compatible_inputs: callback(qname) ->
                list[(input_name, display_name)] of compatible inputs
            is_action_bound: callback(qname, port, input_name) -> bool
            on_action_renamed: callback(old_qname, new_qname) when an action's
                qualified name changes (group or name change) so bindings can
                be updated
            on_selection_changed: callback(qname | None) when tree selection
                changes, allowing external listeners to sync
        """
        super().__init__(parent, padx=5, pady=5)
        self._on_actions_changed = on_actions_changed
        self._on_export_group = on_export_group
        self._on_before_change = on_before_change
        self._on_drag_start = on_drag_start
        self._on_drag_end = on_drag_end
        self._get_binding_info = get_binding_info
        self._on_assign_action = on_assign_action
        self._on_unassign_action = on_unassign_action
        self._on_unassign_all = on_unassign_all
        self._get_all_controllers = get_all_controllers
        self._get_compatible_inputs = get_compatible_inputs
        self._is_action_bound_cb = is_action_bound
        self._on_action_renamed = on_action_renamed
        self._on_selection_changed = on_selection_changed
        self._actions: dict[str, ActionDefinition] = {}
        self._empty_groups: set[str] = set()
        self._selected_name: str | None = None
        self._updating_form = False  # Guard against feedback loops
        self._type_switch_active = False  # True during type-change auto-sets

        # Drag-from-tree state
        self._drag_item: str | None = None
        self._drag_start_pos: tuple[int, int] = (0, 0)
        self._drag_started: bool = False
        self._drag_target_group: str | None = None
        self._drag_highlight_iid: str | None = None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # --- Action Tree ---
        list_frame = ttk.LabelFrame(self, text="Actions", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True)

        # Filter entry
        filter_frame = tk.Frame(list_frame)
        filter_frame.pack(fill=tk.X, pady=(0, 3))
        self._filter_var = tk.StringVar()
        self._filter_entry = ttk.Entry(
            filter_frame, textvariable=self._filter_var, width=20)
        self._filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._filter_var.trace_add("write", self._on_filter_changed)
        self._filter_entry.bind(
            "<Escape>", lambda e: self._clear_filter())
        # Placeholder text
        self._filter_placeholder = True
        self._filter_entry.insert(0, "Filter actions...")
        self._filter_entry.config(foreground="grey")
        self._filter_entry.bind("<FocusIn>", self._on_filter_focus_in)
        self._filter_entry.bind("<FocusOut>", self._on_filter_focus_out)

        # Binding status filter toggles
        self._filter_unassigned_var = tk.BooleanVar()
        self._filter_multi_var = tk.BooleanVar()
        self._filter_unassigned_cb = ttk.Checkbutton(
            filter_frame, text="Unassigned",
            variable=self._filter_unassigned_var,
            command=self._on_status_filter_changed,
        )
        self._filter_unassigned_cb.pack(side=tk.LEFT, padx=(4, 0))
        self._filter_multi_cb = ttk.Checkbutton(
            filter_frame, text="Multi",
            variable=self._filter_multi_var,
            command=self._on_status_filter_changed,
        )
        self._filter_multi_cb.pack(side=tk.LEFT, padx=(2, 0))

        tree_container = tk.Frame(list_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)

        self._tree = ttk.Treeview(tree_container, selectmode="browse", show="tree")
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<<TreeviewOpen>>", self._on_tree_toggle)
        self._tree.bind("<<TreeviewClose>>", self._on_tree_toggle)

        # Drag-from-tree bindings
        self._tree.bind("<ButtonPress-1>", self._on_tree_press)
        self._tree.bind("<B1-Motion>", self._on_tree_drag)
        self._tree.bind("<ButtonRelease-1>", self._on_tree_release)
        self._tree.bind("<MouseWheel>", self._on_tree_scroll)
        self._tree.bind("<Button-4>", self._on_tree_scroll)   # Linux scroll up
        self._tree.bind("<Button-5>", self._on_tree_scroll)   # Linux scroll down
        self._tree.bind("<Delete>", lambda e: self._remove_action())
        self._tree.bind("<Control-d>", lambda e: self._duplicate_action())

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
        self._context_menu.add_command(label="Rename Group...",
                                       command=self._rename_group)
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
        self._assign_btn = ttk.Button(
            btn_frame, text="Assign...",
            command=self._on_assign_button, width=8)
        self._assign_btn.pack(side=tk.LEFT, padx=2)

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
        self._name_label = ttk.Label(self._detail_frame, text="Name:", width=8)
        self._name_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._name_var = tk.StringVar()
        self._name_entry = ttk.Entry(self._detail_frame,
                                     textvariable=self._name_var, width=20)
        self._name_entry.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._name_var.trace_add("write", self._on_name_changed)

        # Group
        row += 1
        self._group_label = ttk.Label(self._detail_frame, text="Group:", width=8)
        self._group_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._group_var = tk.StringVar()
        self._group_combo = ttk.Combobox(self._detail_frame,
                                         textvariable=self._group_var, width=17)
        self._group_combo.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._group_var.trace_add("write", self._on_group_changed)

        # Description (multi-line wrapped text)
        row += 1
        self._desc_label = ttk.Label(self._detail_frame, text="Description:",
                                         width=12)
        self._desc_label.grid(row=row, column=0, sticky=tk.NW, pady=2)
        self._desc_text = tk.Text(self._detail_frame, width=23, height=3,
                                  wrap=tk.WORD, font=("TkDefaultFont", 9),
                                  relief=tk.SUNKEN, borderwidth=1)
        self._desc_text.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._desc_text.bind("<<Modified>>", self._on_desc_modified)

        # Input Type
        row += 1
        self._input_type_label = ttk.Label(self._detail_frame, text="Input Type:",
                                                 width=8, wraplength=55)
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
            values=[t.value for t in BUTTON_EVENT_TRIGGER_MODES],
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

        # Slew rate (axis only)
        row += 1
        self._slew_label = ttk.Label(self._detail_frame, text="Slew Rate:")
        self._slew_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._slew_var = tk.StringVar(value="0.0")
        self._slew_spin = ttk.Spinbox(
            self._detail_frame, textvariable=self._slew_var,
            from_=0.0, to=100.0, increment=0.1, width=17,
        )
        self._slew_spin.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._slew_var.trace_add("write", self._on_field_changed)

        # Negative slew rate (axis only, stored in extra)
        row += 1
        self._neg_slew_frame = ttk.Frame(self._detail_frame)
        self._neg_slew_frame.grid(row=row, column=0, columnspan=2,
                                  sticky=tk.EW, pady=2)
        self._neg_slew_enable_var = tk.BooleanVar(value=False)
        self._neg_slew_check = ttk.Checkbutton(
            self._neg_slew_frame, text="Neg. Slew Rate:",
            variable=self._neg_slew_enable_var,
        )
        self._neg_slew_check.pack(side=tk.LEFT)
        self._neg_slew_var = tk.StringVar(value="0.0")
        self._neg_slew_spin = ttk.Spinbox(
            self._neg_slew_frame, textvariable=self._neg_slew_var,
            from_=-100.0, to=0.0, increment=0.1, width=10,
        )
        self._neg_slew_spin.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._neg_slew_spin.config(state="disabled")
        self._neg_slew_enable_var.trace_add("write", self._on_neg_slew_toggled)
        self._neg_slew_var.trace_add("write", self._on_field_changed)

        # Spline controls (visible only for ANALOG + SPLINE trigger mode)
        row += 1
        self._edit_spline_btn = ttk.Button(
            self._detail_frame, text="Edit Spline...",
            command=self._on_edit_spline,
        )
        self._edit_spline_btn.grid(row=row, column=0, columnspan=2,
                                    sticky=tk.EW, pady=2)

        # Segment controls (visible only for ANALOG + SEGMENTED trigger mode)
        row += 1
        self._edit_segments_btn = ttk.Button(
            self._detail_frame, text="Edit Segments...",
            command=self._on_edit_segments,
        )
        self._edit_segments_btn.grid(row=row, column=0, columnspan=2,
                                     sticky=tk.EW, pady=2)

        self._detail_frame.columnconfigure(1, weight=1)

        # Analog-only widgets for show/hide
        self._axis_widgets = [
            (self._deadband_label, self._deadband_spin),
            (self._inversion_label, self._inversion_check),
            (self._scale_label, self._scale_spin),
            (self._slew_label, self._slew_spin),
        ]
        # Neg slew frame handled separately (single frame spanning both columns)
        self._neg_slew_widgets = [self._neg_slew_frame]

        # Spline-only widgets for show/hide
        self._spline_widgets = [self._edit_spline_btn]
        self._edit_spline_btn.grid_remove()

        # Segment-only widgets for show/hide
        self._segment_widgets = [self._edit_segments_btn]
        self._edit_segments_btn.grid_remove()

        # Tooltips for detail form fields
        _WidgetTooltip(self._name_label, TIP_NAME)
        _WidgetTooltip(self._name_entry, TIP_NAME)
        _WidgetTooltip(self._group_label, TIP_GROUP)
        _WidgetTooltip(self._group_combo, TIP_GROUP)
        _WidgetTooltip(self._desc_label, TIP_DESC)
        _WidgetTooltip(self._desc_text, TIP_DESC)
        _WidgetTooltip(self._input_type_label, TIP_INPUT_TYPE)
        _WidgetTooltip(self._input_type_combo, TIP_INPUT_TYPE)
        self._trigger_tooltip = _WidgetTooltip(
            self._trigger_label, TIP_TRIGGER)
        _WidgetTooltip(self._trigger_combo, TIP_TRIGGER)
        _WidgetTooltip(self._deadband_label, TIP_DEADBAND)
        _WidgetTooltip(self._deadband_spin, TIP_DEADBAND)
        _WidgetTooltip(self._inversion_label, TIP_INVERSION)
        _WidgetTooltip(self._inversion_check, TIP_INVERSION)
        _WidgetTooltip(self._scale_label, TIP_SCALE)
        _WidgetTooltip(self._scale_spin, TIP_SCALE)
        _WidgetTooltip(self._slew_label, TIP_SLEW)
        _WidgetTooltip(self._slew_spin, TIP_SLEW)
        _WidgetTooltip(self._neg_slew_check, TIP_NEG_SLEW)
        _WidgetTooltip(self._neg_slew_spin, TIP_NEG_SLEW)
        _WidgetTooltip(self._edit_spline_btn, TIP_EDIT_SPLINE)
        _WidgetTooltip(self._edit_segments_btn, TIP_EDIT_SEGMENTS)
        # Filter bar tooltips
        _WidgetTooltip(self._filter_entry, TIP_FILTER)
        _WidgetTooltip(self._filter_unassigned_cb, TIP_FILTER_UNASSIGNED)
        _WidgetTooltip(self._filter_multi_cb, TIP_FILTER_MULTI)

        self._set_detail_enabled(False)

    # ------------------------------------------------------------------
    # Custom-settings tracking
    # ------------------------------------------------------------------

    @staticmethod
    def _is_action_custom(action: ActionDefinition) -> bool:
        """Check if an action has any non-default field values.

        Used on load to tag actions that were customized in the YAML.
        """
        if action.input_type == InputType.ANALOG:
            default_trigger = EventTriggerMode.SCALED
        else:
            default_trigger = EventTriggerMode.ON_TRUE
        return (
            action.deadband > 0.01
            or action.inversion
            or abs(action.scale - 1.0) > 0.01
            or action.slew_rate > 0.01
            or action.trigger_mode != default_trigger
            or action.extra.get("spline_points")
            or action.extra.get("segment_points")
            or action.extra.get("negative_slew_rate") is not None
        )

    def _tag_actions_custom(self):
        """Set _has_custom on all actions from current field values."""
        for action in self._actions.values():
            action._has_custom = self._is_action_custom(action)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_actions(self, actions: dict[str, ActionDefinition]):
        """Load a full set of actions (e.g., from file)."""
        self._actions = dict(actions)
        self._tag_actions_custom()
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
        self._refresh_tree()

    # ------------------------------------------------------------------
    # Tree Management
    # ------------------------------------------------------------------

    def _collect_groups(self) -> dict[str, list[str]]:
        """Collect group -> [qualified_name, ...] mapping.

        The "general" group is always included so actions can be
        assigned to it even when it has no members.
        """
        groups: dict[str, list[str]] = {"general": []}
        for qname, action in self._actions.items():
            groups.setdefault(action.group, []).append(qname)
        for g in self._empty_groups:
            if g not in groups:
                groups[g] = []
        return groups

    def _sorted_group_names(self, groups: dict[str, list[str]]) -> list[str]:
        """Sort group names with 'general' first."""
        return sorted(groups.keys(), key=lambda g: (g != "general", g))

    # Prefix for placeholder items in empty groups
    _EMPTY_PREFIX = "empty::"

    def _refresh_tree(self):
        """Rebuild the treeview from the actions dict."""
        self._tree.delete(*self._tree.get_children())

        groups = self._collect_groups()
        sorted_groups = self._sorted_group_names(groups)
        filt = self._get_filter_text()
        status_active = (self._filter_unassigned_var.get()
                         or self._filter_multi_var.get())

        for group in sorted_groups:
            group_iid = f"{self._GROUP_PREFIX}{group}"
            members = groups[group]

            # Apply text filter: keep actions matching name/group/description
            if filt:
                members = [
                    q for q in members
                    if self._matches_filter(q, filt)
                ]
                # Skip groups with no matching actions (unless group
                # name itself matches)
                if not members and filt not in group.lower():
                    continue

            # Apply binding status filter
            if status_active:
                members = [
                    q for q in members
                    if self._matches_status_filter(q)
                ]
                if not members:
                    continue

            has_actions = bool(members)
            self._tree.insert("", tk.END, iid=group_iid,
                              text=f" {group}", open=has_actions,
                              tags=("group",))

            if has_actions:
                for qname in sorted(members,
                                    key=lambda q: q.split(".", 1)[-1]):
                    action = self._actions[qname]
                    self._tree.insert(group_iid, tk.END, iid=qname,
                                      text=f"  {action.name}",
                                      tags=("action",))
            else:
                # Placeholder so the +/- indicator appears
                self._tree.insert(
                    group_iid, tk.END,
                    iid=f"{self._EMPTY_PREFIX}{group}",
                    text="  (empty)", tags=("empty_placeholder",))

        # Update group combo values
        self._group_combo['values'] = sorted_groups

        # Style rows
        self._tree.tag_configure("group", font=("TkDefaultFont", 9, "bold"))
        self._tree.tag_configure("action", font=("TkDefaultFont", 9))
        self._tree.tag_configure("empty_placeholder",
                                 foreground="#999999",
                                 font=("TkDefaultFont", 9, "italic"))

        self.update_binding_tags()

    def update_binding_tags(self):
        """Update action item background colors based on binding status.

        Called after bindings change (drag-drop, dialog, undo, file load).
        - Unassigned actions get a faint red background.
        - Actions bound to more than one input get a faint yellow background.
        - Collapsed groups reflect child status: red (unassigned), yellow
          (duplicate-bound), or orange (both).
        """
        self._tree.tag_configure("unassigned",
                                 background="#ffdddd",
                                 font=("TkDefaultFont", 9))
        self._tree.tag_configure("multi_bound",
                                 background="#ffffcc",
                                 font=("TkDefaultFont", 9))
        self._tree.tag_configure("action",
                                 background="",
                                 font=("TkDefaultFont", 9))
        # Group-level status tags (shown when collapsed)
        self._tree.tag_configure("group_unassigned",
                                 background="#ffdddd",
                                 font=("TkDefaultFont", 9, "bold"))
        self._tree.tag_configure("group_multi_bound",
                                 background="#ffffcc",
                                 font=("TkDefaultFont", 9, "bold"))
        self._tree.tag_configure("group_mixed",
                                 background="#ffddbb",
                                 font=("TkDefaultFont", 9, "bold"))

        if not self._get_binding_info:
            return

        # Track per-group status flags
        group_has_unassigned: dict[str, bool] = {}
        group_has_multi: dict[str, bool] = {}

        for qname, action in self._actions.items():
            if not self._tree.exists(qname):
                continue
            bindings = self._get_binding_info(qname)
            if not bindings:
                self._tree.item(qname, tags=("unassigned",))
                group_has_unassigned[action.group] = True
            elif len(bindings) > 1:
                self._tree.item(qname, tags=("multi_bound",))
                group_has_multi[action.group] = True
            else:
                self._tree.item(qname, tags=("action",))

        # Apply status colors to collapsed group nodes
        self._update_group_tags(group_has_unassigned, group_has_multi)

    def _update_group_tags(self, group_has_unassigned: dict[str, bool],
                           group_has_multi: dict[str, bool]):
        """Set group node tags based on child status and collapsed state."""
        for group_iid in self._tree.get_children(""):
            if not group_iid.startswith(self._GROUP_PREFIX):
                continue
            group_name = group_iid[len(self._GROUP_PREFIX):]
            is_open = self._tree.item(group_iid, "open")
            has_unassigned = group_has_unassigned.get(group_name, False)
            has_multi = group_has_multi.get(group_name, False)

            if not is_open and has_unassigned and has_multi:
                self._tree.item(group_iid, tags=("group_mixed",))
            elif not is_open and has_unassigned:
                self._tree.item(group_iid, tags=("group_unassigned",))
            elif not is_open and has_multi:
                self._tree.item(group_iid, tags=("group_multi_bound",))
            else:
                self._tree.item(group_iid, tags=("group",))

    def _on_tree_toggle(self, event):
        """Handle group expand/collapse — refresh group background colors."""
        self.update_binding_tags()

    # ------------------------------------------------------------------
    # Filter
    # ------------------------------------------------------------------

    def _get_filter_text(self) -> str:
        """Return the active filter string, or '' if placeholder is showing."""
        if self._filter_placeholder:
            return ""
        return self._filter_var.get().strip().lower()

    def _on_filter_changed(self, *args):
        if self._filter_placeholder:
            return
        self._refresh_tree()

    def _clear_filter(self):
        self._filter_var.set("")
        self._filter_unassigned_var.set(False)
        self._filter_multi_var.set(False)
        self._refresh_tree()
        self._tree.focus_set()

    def _on_filter_focus_in(self, event):
        if self._filter_placeholder:
            self._filter_placeholder = False
            self._filter_entry.delete(0, tk.END)
            self._filter_entry.config(foreground="")

    def _on_filter_focus_out(self, event):
        if not self._filter_var.get():
            self._filter_placeholder = True
            self._filter_entry.insert(0, "Filter actions...")
            self._filter_entry.config(foreground="grey")

    def _on_status_filter_changed(self):
        """Handle unassigned/multi-bound filter toggle."""
        self._refresh_tree()

    def _matches_filter(self, qname: str, filt: str) -> bool:
        """Check if an action matches the filter text.

        Supports glob wildcards (* and ?) when present in the filter.
        Falls back to substring matching otherwise.
        """
        action = self._actions.get(qname)
        if not action:
            return False
        fields = (action.name.lower(), action.group.lower(),
                  action.description.lower())
        if '*' in filt or '?' in filt:
            # Auto-append * so users don't need to match through
            # end of string: "de*p" matches "deploy"
            pattern = filt if filt.endswith(('*', '?')) else filt + '*'
            return any(fnmatch.fnmatch(f, pattern) for f in fields)
        return any(filt in f for f in fields)

    def _matches_status_filter(self, qname: str) -> bool:
        """Check if an action passes the binding status filter.

        When neither toggle is active, all actions pass.
        When one or both are active, the action must match at least
        one active filter (OR logic).
        """
        want_unassigned = self._filter_unassigned_var.get()
        want_multi = self._filter_multi_var.get()
        if not want_unassigned and not want_multi:
            return True
        if not self._get_binding_info:
            return True
        bindings = self._get_binding_info(qname)
        if want_unassigned and not bindings:
            return True
        if want_multi and len(bindings) > 1:
            return True
        return False

    # ------------------------------------------------------------------
    # Selection Handling
    # ------------------------------------------------------------------

    def _on_select(self, event):
        """Handle tree selection change."""
        sel = self._tree.selection()
        if not sel:
            self._selected_name = None
            self._set_detail_enabled(False)
            self._notify_selection_changed()
            return

        item_id = sel[0]
        if (item_id.startswith(self._GROUP_PREFIX)
                or item_id.startswith(self._EMPTY_PREFIX)):
            self._selected_name = None
            self._set_detail_enabled(False)
            self._notify_selection_changed()
            return

        self._selected_name = item_id
        self._load_detail(item_id)
        self._set_detail_enabled(True)
        self._notify_selection_changed()

    def _notify_selection_changed(self):
        """Notify external listeners of the current selection."""
        if self._on_selection_changed:
            self._on_selection_changed(self._selected_name)

    def _load_detail(self, qname: str):
        """Populate the detail form from an action."""
        action = self._actions.get(qname)
        if not action:
            return

        self._updating_form = True
        try:
            self._name_var.set(action.name)
            self._group_var.set(action.group)
            self._desc_text.delete("1.0", tk.END)
            self._desc_text.insert("1.0", action.description)
            self._desc_text.edit_modified(False)
            self._input_type_var.set(action.input_type.value)
            self._update_trigger_mode_options(action.input_type)
            self._trigger_var.set(action.trigger_mode.value)
            self._deadband_var.set(str(action.deadband))
            self._inversion_var.set(action.inversion)
            self._scale_var.set(str(action.scale))
            self._slew_var.set(str(action.slew_rate))
            neg_slew = action.extra.get("negative_slew_rate")
            if neg_slew is not None:
                self._neg_slew_enable_var.set(True)
                self._neg_slew_var.set(str(min(float(neg_slew), 0.0)))
            else:
                self._neg_slew_enable_var.set(False)
                self._neg_slew_var.set("0.0")
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
            elif isinstance(child, (ttk.Checkbutton, ttk.Button)):
                child.config(state=state)
        # Handle children inside the neg slew frame (nested in a sub-frame)
        for child in self._neg_slew_frame.winfo_children():
            if isinstance(child, (ttk.Spinbox, ttk.Checkbutton)):
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
            modes = ANALOG_EVENT_TRIGGER_MODES
            default = EventTriggerMode.SCALED
        else:
            modes = BUTTON_EVENT_TRIGGER_MODES
            default = EventTriggerMode.ON_TRUE

        values = [m.value for m in modes]
        self._trigger_combo['values'] = values

        # If current selection isn't valid for the new type, reset to default
        if self._trigger_var.get() not in values:
            self._trigger_var.set(default.value)

    def _update_type_visibility(self):
        """Show/hide fields based on input type and trigger mode.

        Analog-specific fields (deadband, inversion, scale, slew) only shown
        for analog.  When trigger mode is RAW, axis fields are visible but
        disabled (greyed out) since RAW bypasses all shaping.
        Spline controls only shown for analog + spline trigger mode.
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

        # Neg slew frame: show/hide with other axis widgets
        for w in self._neg_slew_widgets:
            if is_analog:
                w.grid()
            else:
                w.grid_remove()

        # Spline controls: visible only for ANALOG + SPLINE
        trigger_str = self._trigger_var.get()
        show_spline = (is_analog
                       and trigger_str == EventTriggerMode.SPLINE.value)
        for w in self._spline_widgets:
            if show_spline:
                w.grid()
            else:
                w.grid_remove()

        # Segment controls: visible only for ANALOG + SEGMENTED
        show_segments = (is_analog
                         and trigger_str == EventTriggerMode.SEGMENTED.value)
        for w in self._segment_widgets:
            if show_segments:
                w.grid()
            else:
                w.grid_remove()

        # Disable axis fields when trigger mode is RAW (bypasses all shaping)
        if is_analog:
            is_raw = trigger_str == EventTriggerMode.RAW.value
            raw_state = "disabled" if is_raw else "normal"
            self._deadband_spin.config(state=raw_state)
            self._inversion_check.config(state=raw_state)
            self._scale_spin.config(state=raw_state)
            self._slew_spin.config(state=raw_state)
            self._neg_slew_check.config(state=raw_state)
            if is_raw:
                self._neg_slew_spin.config(state="disabled")
            else:
                neg_state = ("normal" if self._neg_slew_enable_var.get()
                             else "disabled")
                self._neg_slew_spin.config(state=neg_state)

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
            action.description = self._desc_text.get(
                "1.0", "end-1c").strip()
            action.input_type = InputType(self._input_type_var.get())
            if action.input_type == InputType.OUTPUT:
                action.trigger_mode = EventTriggerMode.RAW
            else:
                action.trigger_mode = EventTriggerMode(self._trigger_var.get())
            action.deadband = float(self._deadband_var.get() or 0)
            action.inversion = self._inversion_var.get()
            action.scale = float(self._scale_var.get() or 1.0)
            action.slew_rate = float(self._slew_var.get() or 0.0)
            if self._neg_slew_enable_var.get():
                val = float(self._neg_slew_var.get() or 0.0)
                action.extra["negative_slew_rate"] = min(val, 0.0)
            else:
                action.extra.pop("negative_slew_rate", None)
        except (ValueError, KeyError):
            return False

        return True

    def _on_desc_modified(self, event=None):
        """Handle description Text widget changes."""
        if not self._desc_text.edit_modified():
            return
        self._desc_text.edit_modified(False)
        if self._updating_form:
            return
        self._on_field_changed()

    def _on_field_changed(self, *args):
        """Handle changes to detail fields (not name or group)."""
        if self._updating_form:
            return
        if self._on_before_change:
            self._on_before_change(500)
        self._update_type_visibility()
        if self._save_detail() and self._on_actions_changed:
            # Mark as user-customized (unless this is an auto-set
            # from a type switch — that resets the flag after)
            if not self._type_switch_active and self._selected_name:
                action = self._actions.get(self._selected_name)
                if action:
                    action._has_custom = True
            self._on_actions_changed()

    def _on_neg_slew_toggled(self, *args):
        """Enable/disable the negative slew rate spinbox."""
        enabled = self._neg_slew_enable_var.get()
        self._neg_slew_spin.config(state="normal" if enabled else "disabled")
        if not self._updating_form:
            self._on_field_changed()

    def _on_input_type_changed(self, *args):
        """Handle input type dropdown change."""
        if not self._updating_form:
            try:
                input_type = InputType(self._input_type_var.get())
            except ValueError:
                input_type = InputType.BUTTON

            # Warn on any input type change if user-customized settings exist
            if self._selected_name:
                action = self._actions.get(self._selected_name)
                if (action and input_type != action.input_type
                        and getattr(action, '_has_custom', False)):
                    if not messagebox.askyesno(
                        "Change Input Type",
                        "Changing input type may reset or\n"
                        "invalidate current settings (deadband,\n"
                        "scale, curves, bindings). Continue?",
                    ):
                        self._updating_form = True
                        try:
                            self._input_type_var.set(
                                action.input_type.value)
                        finally:
                            self._updating_form = False
                        return

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
                else:
                    # Reset analog-specific fields to defaults
                    self._deadband_var.set("0.0")
                    self._inversion_var.set(False)
                    self._scale_var.set("1.0")
                    self._slew_var.set("0.0")
                    self._neg_slew_enable_var.set(False)
                    self._neg_slew_var.set("0.0")
                    action = self._actions.get(self._selected_name)
                    if action:
                        action.extra.pop("spline_points", None)
                        action.extra.pop("segment_points", None)
                        action.extra.pop("negative_slew_rate", None)
                # Update trigger mode options and default
                self._update_trigger_mode_options(input_type)
            finally:
                self._updating_form = False

            # Save fields and update visibility, but suppress the
            # _has_custom flag — type switches reset it to False
            self._type_switch_active = True
            self._update_type_visibility()
            self._on_field_changed()
            self._type_switch_active = False
            action = self._actions.get(self._selected_name)
            if action:
                action._has_custom = False

    def _on_edit_spline(self):
        """Open the spline editor dialog for the selected action."""
        if self._selected_name is None:
            return
        action = self._actions.get(self._selected_name)
        if not action:
            return

        from host.controller_config.spline_editor import (
            SplineEditorDialog, default_points,
        )

        points = action.extra.get("spline_points")
        if not points:
            points = default_points()

        # Collect spline curves from other actions for "Copy from..."
        other_curves = {}
        for qname, act in self._actions.items():
            if qname != self._selected_name:
                pts = act.extra.get("spline_points")
                if pts:
                    other_curves[qname] = pts

        dialog = SplineEditorDialog(self.winfo_toplevel(), points,
                                    other_curves)
        result = dialog.get_result()

        if result is not None:
            if self._on_before_change:
                self._on_before_change(0)
            action.extra["spline_points"] = result
            if self._on_actions_changed:
                self._on_actions_changed()

    def _on_edit_segments(self):
        """Open the segment editor dialog for the selected action."""
        if self._selected_name is None:
            return
        action = self._actions.get(self._selected_name)
        if not action:
            return

        from host.controller_config.segment_editor import (
            SegmentEditorDialog, default_segment_points,
        )

        points = action.extra.get("segment_points")
        if not points:
            points = default_segment_points()

        # Collect segment curves from other actions for "Copy from..."
        other_curves = {}
        for qname, act in self._actions.items():
            if qname != self._selected_name:
                pts = act.extra.get("segment_points")
                if pts:
                    other_curves[qname] = pts

        dialog = SegmentEditorDialog(self.winfo_toplevel(), points,
                                     other_curves)
        result = dialog.get_result()

        if result is not None:
            if self._on_before_change:
                self._on_before_change(0)
            action.extra["segment_points"] = result
            if self._on_actions_changed:
                self._on_actions_changed()

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

        # Update binding references from old to new qualified name
        if self._on_action_renamed and old_qname != new_qname:
            self._on_action_renamed(old_qname, new_qname)

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

        self._move_action_to_group(self._selected_name, new_group)

    def _move_action_to_group(self, qname: str, new_group: str):
        """Move an action to a different group, handling collisions and undo."""
        action = self._actions.get(qname)
        if not action or new_group == action.group:
            return

        if self._on_before_change:
            self._on_before_change(0)

        old_qname = qname
        old_group = action.group
        del self._actions[qname]

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

        # Preserve old group as empty if it has no remaining actions
        if not any(a.group == old_group for a in self._actions.values()):
            self._empty_groups.add(old_group)

        # Remove new group from empty tracking since it now has actions
        self._empty_groups.discard(new_group)

        # Update binding references from old to new qualified name
        if self._on_action_renamed and old_qname != new_qname:
            self._on_action_renamed(old_qname, new_qname)

        self._refresh_tree()
        self._reselect(new_qname)
        self._load_detail(new_qname)

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
        action._has_custom = False
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

    def _rename_group(self):
        """Rename the selected group and update all its actions."""
        old_name = self._get_selected_group_name()
        if not old_name:
            messagebox.showinfo("No Group Selected",
                                "Select a group to rename.")
            return

        new_name = simpledialog.askstring(
            "Rename Group", "New name:", initialvalue=old_name, parent=self)
        if not new_name or not new_name.strip():
            return
        new_name = new_name.strip().lower().replace(" ", "_")

        if new_name == old_name:
            return

        # Validate: no dots allowed in group names
        if "." in new_name:
            messagebox.showerror("Invalid Name",
                                 "Group names cannot contain dots.")
            return

        # Check for collision with existing groups
        groups = self._collect_groups()
        if new_name in groups:
            messagebox.showerror("Group Exists",
                                 f"Group '{new_name}' already exists.")
            return

        if self._on_before_change:
            self._on_before_change(0)

        # Collect actions in this group
        group_actions = [(qn, a) for qn, a in list(self._actions.items())
                         if a.group == old_name]

        # Re-key each action with the new group
        for old_qname, action in group_actions:
            del self._actions[old_qname]
            action.group = new_name
            new_qname = action.qualified_name
            self._actions[new_qname] = action

            if self._on_action_renamed:
                self._on_action_renamed(old_qname, new_qname)

        # Update empty groups tracking
        if old_name in self._empty_groups:
            self._empty_groups.discard(old_name)
            self._empty_groups.add(new_name)

        # Update selection to the renamed group
        if self._selected_name:
            # If the selected action was in this group, update reference
            for old_qname, action in group_actions:
                if self._selected_name == old_qname:
                    self._selected_name = action.qualified_name
                    break

        self._refresh_tree()

        if self._on_actions_changed:
            self._on_actions_changed()

    # ------------------------------------------------------------------
    # Context Menu (Right-Click)
    # ------------------------------------------------------------------

    def _on_assign_button(self):
        """Open the assign context menu from the Assign button."""
        if not self._selected_name:
            return
        if self._selected_name not in self._actions:
            return
        # Position menu at the button
        btn = self._assign_btn
        x = btn.winfo_rootx()
        y = btn.winfo_rooty() + btn.winfo_height()

        class _FakeEvent:
            pass

        evt = _FakeEvent()
        evt.x_root = x
        evt.y_root = y
        self._show_action_context_menu(evt, self._selected_name)

    def _on_right_click(self, event):
        """Show context menu on right-click."""
        item = self._tree.identify_row(event.y)
        if not item:
            return
        if item.startswith(self._GROUP_PREFIX):
            self._tree.selection_set(item)
            self._context_menu.post(event.x_root, event.y_root)
        elif item in self._actions:
            self._tree.selection_set(item)
            self._show_action_context_menu(event, item)

    def _show_action_context_menu(self, event, qname: str):
        """Build and show a context menu for an action item.

        Shows each controller as a submenu with its compatible inputs.
        Bound inputs have a checkmark and clicking unassigns them.
        Unbound inputs are plain and clicking assigns them.
        """
        if not (self._get_all_controllers and self._get_compatible_inputs):
            return

        controllers = self._get_all_controllers()
        compatible = self._get_compatible_inputs(qname)

        menu = tk.Menu(self, tearoff=0)
        has_any_binding = False

        for port, ctrl_name in controllers:
            sub = tk.Menu(menu, tearoff=0)
            has_bound = False
            has_unbound = False
            bound_items = []
            unbound_items = []

            for input_name, display_name in compatible:
                # Check if this action is bound to this input on this port
                is_bound = self._is_action_bound(
                    qname, port, input_name)
                if is_bound:
                    has_bound = True
                    has_any_binding = True
                    bound_items.append((input_name, display_name))
                else:
                    has_unbound = True
                    unbound_items.append((input_name, display_name))

            # Add bound inputs first (with checkmark)
            for input_name, display_name in bound_items:
                sub.add_command(
                    label=f"\u2713 {display_name}",
                    command=lambda q=qname, p=port, n=input_name:
                        self._on_unassign_action(q, p, n)
                        if self._on_unassign_action else None,
                )

            # Separator between bound and unbound
            if has_bound and has_unbound:
                sub.add_separator()

            # Add unbound compatible inputs
            for input_name, display_name in unbound_items:
                sub.add_command(
                    label=display_name,
                    command=lambda q=qname, p=port, n=input_name:
                        self._on_assign_action(q, p, n)
                        if self._on_assign_action else None,
                )

            label = f"{ctrl_name} (Port {port})"
            menu.add_cascade(label=label, menu=sub)

        menu.add_separator()
        menu.add_command(
            label="Remove from All Inputs",
            command=lambda q=qname:
                self._on_unassign_all(q)
                if self._on_unassign_all else None,
            state=tk.NORMAL if has_any_binding else tk.DISABLED,
        )

        menu.tk_popup(event.x_root, event.y_root)

    def _is_action_bound(self, qname: str, port: int,
                         input_name: str) -> bool:
        """Check if an action is bound to a specific input on a port."""
        if self._is_action_bound_cb:
            return self._is_action_bound_cb(qname, port, input_name)
        return False

    def _on_context_export_group(self):
        """Handle 'Export Group...' from context menu."""
        group = self._get_selected_group_name()
        if group and self._on_export_group:
            self._on_export_group(group)

    # ------------------------------------------------------------------
    # Drag-from-Tree (cross-widget drag-and-drop)
    # ------------------------------------------------------------------

    def _on_tree_scroll(self, event):
        """Cancel any drag (pending or active) when the user scrolls.

        Scrolling shifts items under the cursor, so a release after
        scrolling could target the wrong group.
        """
        if self._drag_item:
            if self._drag_started and self._on_drag_end:
                self._on_drag_end()
            self._drag_item = None
            self._drag_started = False
            self._drag_target_group = None
            self._clear_drag_highlight()

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

        if not self._drag_started:
            dx = event.x_root - self._drag_start_pos[0]
            dy = event.y_root - self._drag_start_pos[1]
            if (dx * dx + dy * dy) < self._DRAG_THRESHOLD ** 2:
                return
            self._drag_started = True
            if self._on_drag_start:
                self._on_drag_start(self._drag_item)

        # Track intra-tree group target for visual feedback
        # Only consider intra-tree drops when mouse is inside the tree widget;
        # implicit grab delivers events even when the mouse is over other widgets
        if self._is_over_tree(event):
            item = self._tree.identify_row(event.y)
            target_group = self._resolve_group_for_item(item)
        else:
            target_group = None

        action = self._actions.get(self._drag_item)
        source_group = action.group if action else None

        if target_group and target_group != source_group:
            group_iid = f"{self._GROUP_PREFIX}{target_group}"
            self._set_drag_highlight(group_iid)
        else:
            self._clear_drag_highlight()
        self._drag_target_group = target_group

    def _on_tree_release(self, event):
        """Handle release — move action to target group or let app handle."""
        drag_item = self._drag_item
        was_dragging = self._drag_started

        # Reset all local drag state
        self._drag_item = None
        self._drag_started = False
        self._drag_target_group = None
        self._clear_drag_highlight()

        if not was_dragging or not drag_item:
            return

        # Check if released over a group in the tree (not outside the widget)
        if not self._is_over_tree(event):
            return

        item = self._tree.identify_row(event.y)
        target_group = self._resolve_group_for_item(item)

        action = self._actions.get(drag_item)
        if action and target_group and target_group != action.group:
            # Cancel cross-widget drag before moving
            if self._on_drag_end:
                self._on_drag_end()
            self._move_action_to_group(drag_item, target_group)

    def _set_drag_highlight(self, group_iid: str):
        """Highlight a group node as a drop target."""
        if group_iid == self._drag_highlight_iid:
            return
        self._clear_drag_highlight()
        if group_iid and self._tree.exists(group_iid):
            self._tree.tag_configure(
                "drop_target",
                background="#cce5ff",
                font=("TkDefaultFont", 9, "bold"))
            self._tree.item(group_iid, tags=("group", "drop_target"))
            self._drag_highlight_iid = group_iid

    def _clear_drag_highlight(self):
        """Remove drop target highlight."""
        if self._drag_highlight_iid and self._tree.exists(
                self._drag_highlight_iid):
            self._tree.item(self._drag_highlight_iid, tags=("group",))
        self._drag_highlight_iid = None

    # ------------------------------------------------------------------
    # Helpers

    def _is_over_tree(self, event) -> bool:
        """Check if event coordinates are within the tree widget bounds."""
        return (0 <= event.x <= self._tree.winfo_width()
                and 0 <= event.y <= self._tree.winfo_height())

    def _resolve_group_for_item(self, item: str | None) -> str | None:
        """Return the group name for a tree item, or None."""
        if not item:
            return None
        if item.startswith(self._GROUP_PREFIX):
            return item[len(self._GROUP_PREFIX):]
        if item.startswith(self._EMPTY_PREFIX):
            return item[len(self._EMPTY_PREFIX):]
        if item in self._actions:
            return self._actions[item].group
        return None
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
            group_actions = [a for a in self._actions.values()
                             if a.group == group]
            count = len(group_actions)
            lines = [f"{group} ({count} action{'s' if count != 1 else ''})"]

            if self._get_binding_info and group_actions:
                unassigned = 0
                multi_bound = 0
                for a in group_actions:
                    bindings = self._get_binding_info(a.qualified_name)
                    if not bindings:
                        unassigned += 1
                    elif len(bindings) > 1:
                        multi_bound += 1
                if unassigned:
                    lines.append(
                        f"{unassigned} unassigned")
                if multi_bound:
                    lines.append(
                        f"{multi_bound} bound to multiple inputs")

            return "\n".join(lines)

        action = self._actions.get(item_id)
        if not action:
            return None

        lines = [action.qualified_name]
        if action.description:
            lines.append(action.description)

        # Show binding assignments
        if self._get_binding_info:
            bindings = self._get_binding_info(item_id)
            if bindings:
                lines.append("")
                lines.append("Assigned to:")
                for ctrl_name, input_display in bindings:
                    lines.append(f"  {ctrl_name} > {input_display}")
                if len(bindings) > 1:
                    lines.append("")
                    lines.append("[Yellow: bound to multiple inputs]")
            else:
                lines.append("")
                lines.append("Not assigned to any input")
                lines.append("[Red: unassigned]")

        return "\n".join(lines)

    def _reselect(self, qname: str):
        """Select and scroll to an item in the tree."""
        if self._tree.exists(qname):
            self._tree.selection_set(qname)
            self._tree.see(qname)
