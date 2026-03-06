"""Action Editor tab with detailed panes for editing action properties.

Three-pane upper section: Common settings (left), Assigned Inputs (center),
and a swappable Button/Analog options pane (right) that switches based on
input type.  Lower section: curve editor (left) and preview widget (right).
"""

import tkinter as tk
from tkinter import ttk, messagebox

from .action_panel import _WidgetTooltip
from .preview_widget import PreviewWidget
from .tooltips import (
    TIP_NAME, TIP_GROUP, TIP_DESC, TIP_INPUT_TYPE,
    TIP_TRIGGER_BUTTON, TIP_TRIGGER_ANALOG, TIP_THRESHOLD,
    TIP_DEADBAND, TIP_INVERSION, TIP_SCALE, TIP_SLEW, TIP_NEG_SLEW,
    TIP_ASSIGN_INPUT, TIP_ASSIGN_BTN, TIP_BOUND_LIST, TIP_UNASSIGN_BTN,
    TIP_VA_BUTTON_MODE, TIP_VA_RAMP_RATE, TIP_VA_ACCELERATION,
    TIP_VA_TARGET, TIP_VA_REST,
    TIP_VA_ZERO_VEL, TIP_VA_NEG_RAMP, TIP_VA_NEG_ACCEL,
)

from utils.controller.model import (
    ANALOG_EVENT_TRIGGER_MODES,
    ActionDefinition,
    BUTTON_EVENT_TRIGGER_MODES,
    EXTRA_NEGATIVE_SLEW_RATE,
    EXTRA_SEGMENT_POINTS,
    EXTRA_SPLINE_POINTS,
    EXTRA_VA_RAMP_RATE,
    EXTRA_VA_ACCELERATION,
    EXTRA_VA_NEGATIVE_RAMP_RATE,
    EXTRA_VA_NEGATIVE_ACCELERATION,
    EXTRA_VA_ZERO_VEL_ON_RELEASE,
    EXTRA_VA_TARGET_VALUE,
    EXTRA_VA_REST_VALUE,
    EXTRA_VA_BUTTON_MODE,
    InputType,
    EventTriggerMode,
    STICK_PAIRS,
    validate_action_name,
    validate_action_group,
)


# ---------------------------------------------------------------------------
# Active/inactive pane styling
# ---------------------------------------------------------------------------

_ACTIVE_FG = "#228B22"      # Forest green for active pane label
_INACTIVE_FG = "#999999"    # Grey for inactive pane label


def _configure_styles():
    """Register ttk styles for active/inactive panes (call once)."""
    style = ttk.Style()
    style.configure("Active.TLabelframe.Label", foreground=_ACTIVE_FG)
    style.configure("Inactive.TLabelframe.Label", foreground=_INACTIVE_FG)


def _set_children_state(widget, state: str):
    """Recursively set state on all interactive children of *widget*."""
    for child in widget.winfo_children():
        try:
            if isinstance(child, ttk.Combobox):
                child.config(state="readonly" if state == "normal" else state)
            else:
                child.config(state=state)
        except tk.TclError:
            pass  # Some widgets don't support the 'state' option
        _set_children_state(child, state)


# ---------------------------------------------------------------------------
# ActionEditorTab
# ---------------------------------------------------------------------------

class ActionEditorTab(ttk.Frame):
    """Detailed action editor shown as a notebook tab.

    Upper section has three panes: Common (left), Assigned Inputs (center),
    and a swappable Button/Analog options pane (right).
    Lower section has placeholders for future curve editor and preview.
    """

    def __init__(self, parent, *,
                 on_before_change=None,
                 on_field_changed=None,
                 get_binding_info=None,
                 on_assign_action=None,
                 on_unassign_action=None,
                 get_all_controllers=None,
                 get_compatible_inputs=None,
                 is_action_bound=None,
                 get_all_actions=None,
                 get_group_names=None,
                 get_advanced_flags=None,
                 icon_loader=None):
        super().__init__(parent)
        _configure_styles()

        self._on_before_change = on_before_change
        self._on_field_changed = on_field_changed
        self._get_all_actions = get_all_actions
        self._get_group_names = get_group_names
        self._get_advanced_flags = get_advanced_flags or (
            lambda: {"splines": True, "nonmono": True})
        self._get_binding_info = get_binding_info
        self._on_assign_action = on_assign_action
        self._on_unassign_action = on_unassign_action
        self._get_all_controllers = get_all_controllers
        self._get_compatible_inputs = get_compatible_inputs
        self._is_action_bound = is_action_bound
        self._icon_loader = icon_loader
        self._binding_icons: list = []  # Prevent GC of PhotoImage refs

        self._action: ActionDefinition | None = None
        self._qname: str | None = None
        self._updating_form = False
        self._type_switch_active = False

        self._assign_map: dict[str, tuple[int, str]] = {}
        self._bound_map: dict[str, tuple[int, str]] = {}

        self._build_ui()
        self._set_all_enabled(False)

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    # Minimum pane fraction (20% of total paned window dimension)
    _MIN_PANE_FRAC = 0.20
    _MIN_UPPER_H = 100   # upper section min height (px)
    _MIN_LOWER_H = 150   # lower section min height (px)

    def _build_ui(self):
        # Top/bottom split — upper gets less weight so lower has more room
        self._vpaned = tk.PanedWindow(
            self, orient=tk.VERTICAL, sashwidth=5, sashrelief=tk.RAISED)
        self._vpaned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # --- Upper section: 3 panes ---
        upper = ttk.Frame(self._vpaned)
        self._vpaned.add(upper, minsize=self._MIN_UPPER_H)

        self._hpaned = tk.PanedWindow(
            upper, orient=tk.HORIZONTAL, sashwidth=5, sashrelief=tk.RAISED)
        self._hpaned.pack(fill=tk.BOTH, expand=True)

        self._build_common_pane(self._hpaned)
        self._build_bindings_pane(self._hpaned)
        self._build_options_pane(self._hpaned)

        # Set sash positions once the paned window is visible and sized
        self._saved_sash: list[int] | None = None
        self._sash_applied = False
        self._hpaned.bind("<Configure>", self._on_h_configure)

        # --- Lower section ---
        lower = ttk.Frame(self._vpaned)
        self._vpaned.add(lower, minsize=self._MIN_LOWER_H)
        self._build_lower_section(lower)
        self._setup_tooltips()

        # Dynamically update minsize on resize to enforce 20% minimum
        self._lower_paned.bind("<Configure>", self._update_lower_minsize)

    def _setup_tooltips(self):
        """Attach tooltip help text to all labels and fields."""
        _tip = _WidgetTooltip
        # --- Common pane ---
        _tip(self._name_label, TIP_NAME)
        _tip(self._name_entry, TIP_NAME)
        _tip(self._group_label, TIP_GROUP)
        _tip(self._group_combo, TIP_GROUP)
        _tip(self._desc_label, TIP_DESC)
        _tip(self._desc_text, TIP_DESC)
        _tip(self._type_label, TIP_INPUT_TYPE)
        # --- Bindings pane ---
        _tip(self._assign_label, TIP_ASSIGN_INPUT)
        _tip(self._assign_combo, TIP_ASSIGN_INPUT)
        _tip(self._assign_btn, TIP_ASSIGN_BTN)
        _tip(self._bound_tree, TIP_BOUND_LIST)
        _tip(self._unassign_btn, TIP_UNASSIGN_BTN)
        # --- Button options pane ---
        _tip(self._btn_trigger_label, TIP_TRIGGER_BUTTON)
        _tip(self._btn_trigger_combo, TIP_TRIGGER_BUTTON)
        # --- Analog options pane ---
        _tip(self._analog_trigger_label, TIP_TRIGGER_ANALOG)
        _tip(self._analog_trigger_combo, TIP_TRIGGER_ANALOG)
        _tip(self._deadband_label, TIP_DEADBAND)
        _tip(self._deadband_spin, TIP_DEADBAND)
        _tip(self._inversion_label, TIP_INVERSION)
        _tip(self._inversion_check, TIP_INVERSION)
        _tip(self._scale_label, TIP_SCALE)
        _tip(self._scale_spin, TIP_SCALE)
        _tip(self._slew_label, TIP_SLEW)
        _tip(self._slew_spin, TIP_SLEW)
        _tip(self._neg_slew_check, TIP_NEG_SLEW)
        _tip(self._neg_slew_spin, TIP_NEG_SLEW)
        # --- Virtual Analog options pane ---
        _tip(self._va_trigger_label, TIP_TRIGGER_ANALOG)
        _tip(self._va_trigger_combo, TIP_TRIGGER_ANALOG)

    def _on_h_configure(self, event):
        """Handle upper paned window configure: restore sash + update minsize."""
        pw = self._hpaned
        w = pw.winfo_width()
        if w < 50:
            return
        # Update dynamic minsize (20% of current width, capped at 30%)
        mn = max(80, int(w * min(self._MIN_PANE_FRAC, 0.30)))
        for child in (self._common_frame, self._bindings_frame,
                      self._options_container):
            try:
                pw.paneconfigure(child, minsize=mn)
            except Exception:
                pass  # Pane may not be mapped yet during layout
        # First configure: restore saved sash positions or default to 33% each
        # Use after_idle so minsize settles before we place sashes.
        if not self._sash_applied:
            self._sash_applied = True
            self.after_idle(self._apply_saved_sash, w)

    def _apply_saved_sash(self, fallback_w):
        """Apply saved sash positions (deferred so minsize is settled)."""
        pw = self._hpaned
        if self._saved_sash:
            try:
                for i, pos in enumerate(self._saved_sash):
                    pw.sash_place(i, pos, 0)
                return
            except Exception:
                pass
        third = fallback_w // 3
        pw.sash_place(0, third, 0)
        pw.sash_place(1, third * 2, 0)

    def set_sash_positions(self, positions: list[int]):
        """Store saved sash positions to apply on first configure."""
        self._saved_sash = positions

    def _update_lower_minsize(self, _event=None):
        """Update native minsize on lower 2 panes to 28% of current width."""
        pw = self._lower_paned
        w = pw.winfo_width()
        if w < 50:
            return
        mn = max(120, int(w * self._MIN_PANE_FRAC))
        for child in pw.panes():
            try:
                pw.paneconfigure(child, minsize=mn)
            except Exception:
                pass  # Pane may not be mapped yet during layout

    # --- Common Pane (left, compact) ---

    def _build_common_pane(self, parent):
        self._common_frame = ttk.LabelFrame(
            parent, text="Action", padding=6)
        parent.add(self._common_frame, minsize=80, stretch="always")

        self._common_frame.columnconfigure(1, weight=1)

        row = 0
        # Name
        self._name_label = ttk.Label(
            self._common_frame, text="Name:", width=8)
        self._name_label.grid(row=row, column=0, sticky=tk.W, pady=1)
        self._name_var = tk.StringVar()
        self._name_entry = ttk.Entry(
            self._common_frame, textvariable=self._name_var, width=17)
        self._name_entry.grid(row=row, column=1, sticky=tk.EW, pady=1)
        # Name commits on focus-out/Enter, not on every keystroke
        self._name_entry.bind("<Return>", self._commit_name_group)
        self._name_entry.bind("<FocusOut>", self._commit_name_group)

        # Group
        row += 1
        self._group_label = ttk.Label(
            self._common_frame, text="Group:", width=8)
        self._group_label.grid(row=row, column=0, sticky=tk.W, pady=1)
        self._group_var = tk.StringVar()
        self._group_combo = ttk.Combobox(
            self._common_frame, textvariable=self._group_var, width=15)
        self._group_combo.grid(row=row, column=1, sticky=tk.EW, pady=1)
        # Group commits on focus-out/Enter/selection, not on every keystroke
        self._group_combo.bind("<Return>", self._commit_name_group)
        self._group_combo.bind("<FocusOut>", self._commit_name_group)
        self._group_combo.bind("<<ComboboxSelected>>",
                               self._commit_name_group)

        # Description (multi-line wrapped text)
        row += 1
        self._desc_label = ttk.Label(
            self._common_frame, text="Desc:", width=8)
        self._desc_label.grid(row=row, column=0, sticky=tk.NW, pady=1)
        self._desc_text = tk.Text(
            self._common_frame, width=1, height=3, wrap=tk.WORD,
            font=("TkDefaultFont", 9), relief=tk.SUNKEN, borderwidth=1)
        self._desc_text.grid(row=row, column=1, sticky=tk.NSEW, pady=1)
        self._desc_text.bind(
            "<<Modified>>", self._on_desc_modified)

        # Input Type (radio buttons, compact)
        row += 1
        self._type_label = ttk.Label(
            self._common_frame, text="Type:", width=8)
        self._type_label.grid(row=row, column=0, sticky=tk.NW, pady=1)
        self._input_type_var = tk.StringVar()
        type_frame = ttk.Frame(self._common_frame)
        type_frame.grid(row=row, column=1, sticky=tk.W, pady=1)
        self._input_type_radios = []
        for itype in InputType:
            rb = ttk.Radiobutton(
                type_frame, text=itype.value.replace("_", " ").title(),
                variable=self._input_type_var, value=itype.value)
            rb.pack(anchor=tk.W, pady=0)
            self._input_type_radios.append(rb)
        self._input_type_var.trace_add(
            "write", self._on_input_type_changed_trace)

        self._common_frame.columnconfigure(1, weight=1)

    # --- Bindings Pane (center) ---

    def _build_bindings_pane(self, parent):
        self._bindings_frame = ttk.LabelFrame(
            parent, text="Assigned Inputs", padding=6)
        parent.add(self._bindings_frame, minsize=80, stretch="always")

        # Assign input
        row = 0
        self._assign_label = ttk.Label(
            self._bindings_frame, text="Assign:")
        self._assign_label.grid(row=row, column=0, sticky=tk.W, pady=1)
        assign_frame = ttk.Frame(self._bindings_frame)
        assign_frame.grid(row=row, column=1, sticky=tk.EW, pady=1)
        self._assign_var = tk.StringVar()
        self._assign_combo = ttk.Combobox(
            assign_frame, textvariable=self._assign_var,
            state="readonly", width=18)
        self._assign_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._assign_btn = ttk.Button(
            assign_frame, text="+", width=3, command=self._on_assign)
        self._assign_btn.pack(side=tk.LEFT, padx=(4, 0))

        # Assigned inputs treeview (double-click to remove)
        row += 1
        style = ttk.Style()
        style.configure("BoundInputs.Treeview",
                         rowheight=26,
                         font=("TkDefaultFont", 10))
        self._bound_tree = ttk.Treeview(
            self._bindings_frame, height=5,
            selectmode="browse", show="tree",
            style="BoundInputs.Treeview")
        self._bound_tree.grid(
            row=row, column=0, columnspan=2, sticky=tk.NSEW, pady=(4, 2))
        self._bound_tree.bind("<Double-1>", lambda e: self._on_unassign())
        scrollbar = ttk.Scrollbar(
            self._bindings_frame, orient=tk.VERTICAL,
            command=self._bound_tree.yview)
        scrollbar.grid(row=row, column=2, sticky=tk.NS, pady=(4, 2))
        self._bound_tree.config(yscrollcommand=scrollbar.set)

        row += 1
        self._unassign_btn = ttk.Button(
            self._bindings_frame, text="- Remove",
            command=self._on_unassign)
        self._unassign_btn.grid(row=row, column=0, sticky=tk.W, pady=1)

        self._bindings_frame.columnconfigure(1, weight=1)
        self._bindings_frame.rowconfigure(1, weight=1)

    # --- Swappable Options Pane (right) ---

    def _build_options_pane(self, parent):
        """Build button and analog frames that swap in the right pane."""
        # Container frame that holds whichever is active
        self._options_container = ttk.Frame(parent)
        parent.add(self._options_container, minsize=80, stretch="always")

        self._build_button_options()
        self._build_analog_options()
        self._build_va_options()

        # Start with neither visible
        self._active_options = None

    def _build_button_options(self):
        self._button_frame = ttk.LabelFrame(
            self._options_container, text="Button Options", padding=6,
            style="Inactive.TLabelframe")

        row = 0
        self._btn_trigger_label = ttk.Label(
            self._button_frame, text="Trigger Mode:")
        self._btn_trigger_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._btn_trigger_var = tk.StringVar()
        self._btn_trigger_combo = ttk.Combobox(
            self._button_frame, textvariable=self._btn_trigger_var,
            values=[m.value for m in BUTTON_EVENT_TRIGGER_MODES],
            state="readonly", width=18)
        self._btn_trigger_combo.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._btn_trigger_var.trace_add(
            "write", self._on_field_changed_trace)

        row += 1
        self._threshold_label = ttk.Label(
            self._button_frame, text="Threshold:")
        self._threshold_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._threshold_var = tk.StringVar(value="0.5")
        self._threshold_spin = ttk.Spinbox(
            self._button_frame, textvariable=self._threshold_var,
            from_=0.0, to=1.0, increment=0.05, width=18)
        self._threshold_spin.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._threshold_var.trace_add(
            "write", self._on_field_changed_trace)
        _WidgetTooltip(self._threshold_label, TIP_THRESHOLD)
        _WidgetTooltip(self._threshold_spin, TIP_THRESHOLD)

        row += 1
        self._btn_info_label = ttk.Label(
            self._button_frame,
            text="Select a button-type action\nto edit trigger options.",
            foreground="#888888", justify=tk.CENTER)
        self._btn_info_label.grid(
            row=row, column=0, columnspan=2, sticky=tk.NSEW, pady=10)

        self._button_frame.columnconfigure(1, weight=1)

    def _build_analog_options(self):
        self._analog_frame = ttk.LabelFrame(
            self._options_container, text="Analog Options", padding=6,
            style="Inactive.TLabelframe")

        row = 0
        self._analog_trigger_label = ttk.Label(
            self._analog_frame, text="Trigger Mode:")
        self._analog_trigger_label.grid(
            row=row, column=0, sticky=tk.W, pady=2)
        self._analog_trigger_var = tk.StringVar()
        self._analog_trigger_combo = ttk.Combobox(
            self._analog_frame, textvariable=self._analog_trigger_var,
            values=[m.value for m in ANALOG_EVENT_TRIGGER_MODES],
            state="readonly", width=18)
        self._analog_trigger_combo.grid(
            row=row, column=1, sticky=tk.EW, pady=2)
        self._analog_trigger_var.trace_add(
            "write", self._on_field_changed_trace)
        self._analog_trigger_var.trace_add(
            "write", self._check_spline_gate)

        row += 1
        self._deadband_label = ttk.Label(
            self._analog_frame, text="Deadband:")
        self._deadband_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._deadband_var = tk.StringVar(value="0.0")
        self._deadband_spin = ttk.Spinbox(
            self._analog_frame, textvariable=self._deadband_var,
            from_=0.0, to=1.0, increment=0.01, width=17)
        self._deadband_spin.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._deadband_var.trace_add("write", self._on_field_changed_trace)

        row += 1
        self._inversion_label = ttk.Label(
            self._analog_frame, text="Inversion:")
        self._inversion_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._inversion_var = tk.BooleanVar(value=False)
        self._inversion_check = ttk.Checkbutton(
            self._analog_frame, variable=self._inversion_var)
        self._inversion_check.grid(row=row, column=1, sticky=tk.W, pady=2)
        self._inversion_var.trace_add("write", self._on_field_changed_trace)

        row += 1
        self._scale_label = ttk.Label(
            self._analog_frame, text="Scale:")
        self._scale_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._scale_var = tk.StringVar(value="1.0")
        self._scale_spin = ttk.Spinbox(
            self._analog_frame, textvariable=self._scale_var,
            from_=-10.0, to=10.0, increment=0.1, width=17)
        self._scale_spin.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._scale_var.trace_add("write", self._on_field_changed_trace)

        row += 1
        self._slew_label = ttk.Label(
            self._analog_frame, text="Slew Rate:")
        self._slew_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._slew_var = tk.StringVar(value="0.0")
        self._slew_spin = ttk.Spinbox(
            self._analog_frame, textvariable=self._slew_var,
            from_=0.0, to=100.0, increment=0.1, width=17)
        self._slew_spin.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._slew_var.trace_add("write", self._on_field_changed_trace)

        row += 1
        self._neg_slew_frame = ttk.Frame(self._analog_frame)
        self._neg_slew_frame.grid(
            row=row, column=0, columnspan=2, sticky=tk.EW, pady=2)
        self._neg_slew_enable_var = tk.BooleanVar(value=False)
        self._neg_slew_check = ttk.Checkbutton(
            self._neg_slew_frame, text="Neg. Slew Rate:",
            variable=self._neg_slew_enable_var)
        self._neg_slew_check.pack(side=tk.LEFT)
        self._neg_slew_var = tk.StringVar(value="0.0")
        self._neg_slew_spin = ttk.Spinbox(
            self._neg_slew_frame, textvariable=self._neg_slew_var,
            from_=-100.0, to=0.0, increment=0.1, width=10)
        self._neg_slew_spin.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._neg_slew_enable_var.trace_add(
            "write", self._on_neg_slew_toggled)
        self._neg_slew_var.trace_add("write", self._on_field_changed_trace)

        self._axis_widgets = [
            self._deadband_spin,
            self._inversion_check,
            self._scale_spin,
            self._slew_spin,
            self._neg_slew_check,
            self._neg_slew_spin,
        ]

        self._analog_frame.columnconfigure(1, weight=1)

    def _build_va_options(self):
        self._va_frame = ttk.LabelFrame(
            self._options_container, text="Virtual Analog Options", padding=6,
            style="Inactive.TLabelframe")

        # Two-column layout: left = generator params, right = shaping
        self._va_left = ttk.Frame(self._va_frame)
        self._va_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        self._va_right = ttk.Frame(self._va_frame)
        self._va_right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0))

        # --- Left column: VA generator fields ---
        row = 0
        lbl = ttk.Label(self._va_left, text="Button Mode:")
        lbl.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._va_mode_var = tk.StringVar(value="held")
        self._va_mode_combo = ttk.Combobox(
            self._va_left, textvariable=self._va_mode_var,
            values=["held", "toggle"], state="readonly", width=10)
        self._va_mode_combo.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._va_mode_var.trace_add("write", self._on_field_changed_trace)
        _WidgetTooltip(lbl, TIP_VA_BUTTON_MODE)
        _WidgetTooltip(self._va_mode_combo, TIP_VA_BUTTON_MODE)

        row += 1
        lbl = ttk.Label(self._va_left, text="Ramp Rate:")
        lbl.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._va_ramp_var = tk.StringVar(value="1.0")
        self._va_ramp_spin = ttk.Spinbox(
            self._va_left, textvariable=self._va_ramp_var,
            from_=0.0, to=100.0, increment=0.1, width=10)
        self._va_ramp_spin.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._va_ramp_var.trace_add("write", self._on_field_changed_trace)
        _WidgetTooltip(lbl, TIP_VA_RAMP_RATE)
        _WidgetTooltip(self._va_ramp_spin, TIP_VA_RAMP_RATE)

        row += 1
        lbl = ttk.Label(self._va_left, text="Acceleration:")
        lbl.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._va_accel_var = tk.StringVar(value="0.0")
        self._va_accel_spin = ttk.Spinbox(
            self._va_left, textvariable=self._va_accel_var,
            from_=0.0, to=100.0, increment=0.1, width=10)
        self._va_accel_spin.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._va_accel_var.trace_add("write", self._on_field_changed_trace)
        _WidgetTooltip(lbl, TIP_VA_ACCELERATION)
        _WidgetTooltip(self._va_accel_spin, TIP_VA_ACCELERATION)

        row += 1
        lbl = ttk.Label(self._va_left, text="Target:")
        lbl.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._va_target_var = tk.StringVar(value="1.0")
        self._va_target_spin = ttk.Spinbox(
            self._va_left, textvariable=self._va_target_var,
            from_=-10.0, to=10.0, increment=0.1, width=10)
        self._va_target_spin.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._va_target_var.trace_add("write", self._on_field_changed_trace)
        _WidgetTooltip(lbl, TIP_VA_TARGET)
        _WidgetTooltip(self._va_target_spin, TIP_VA_TARGET)

        row += 1
        lbl = ttk.Label(self._va_left, text="Rest:")
        lbl.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._va_rest_var = tk.StringVar(value="0.0")
        self._va_rest_spin = ttk.Spinbox(
            self._va_left, textvariable=self._va_rest_var,
            from_=-10.0, to=10.0, increment=0.1, width=10)
        self._va_rest_spin.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._va_rest_var.trace_add("write", self._on_field_changed_trace)
        _WidgetTooltip(lbl, TIP_VA_REST)
        _WidgetTooltip(self._va_rest_spin, TIP_VA_REST)

        row += 1
        self._va_zero_vel_var = tk.BooleanVar(value=False)
        self._va_zero_vel_check = ttk.Checkbutton(
            self._va_left, text="Zero vel on release",
            variable=self._va_zero_vel_var)
        self._va_zero_vel_check.grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=2)
        self._va_zero_vel_var.trace_add(
            "write", self._on_field_changed_trace)
        _WidgetTooltip(self._va_zero_vel_check, TIP_VA_ZERO_VEL)

        row += 1
        self._va_neg_ramp_enable_var = tk.BooleanVar(value=False)
        self._va_neg_ramp_check = ttk.Checkbutton(
            self._va_left, text="Neg Ramp:",
            variable=self._va_neg_ramp_enable_var)
        self._va_neg_ramp_check.grid(row=row, column=0, sticky=tk.W)
        self._va_neg_ramp_var = tk.StringVar(value="0.0")
        self._va_neg_ramp_spin = ttk.Spinbox(
            self._va_left, textvariable=self._va_neg_ramp_var,
            from_=0.0, to=100.0, increment=0.1, width=10)
        self._va_neg_ramp_spin.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._va_neg_ramp_spin.config(state="disabled")
        self._va_neg_ramp_enable_var.trace_add(
            "write", self._on_va_neg_ramp_toggled)
        self._va_neg_ramp_var.trace_add(
            "write", self._on_field_changed_trace)
        _WidgetTooltip(self._va_neg_ramp_check, TIP_VA_NEG_RAMP)
        _WidgetTooltip(self._va_neg_ramp_spin, TIP_VA_NEG_RAMP)

        row += 1
        self._va_neg_accel_enable_var = tk.BooleanVar(value=False)
        self._va_neg_accel_check = ttk.Checkbutton(
            self._va_left, text="Neg Accel:",
            variable=self._va_neg_accel_enable_var)
        self._va_neg_accel_check.grid(row=row, column=0, sticky=tk.W)
        self._va_neg_accel_var = tk.StringVar(value="0.0")
        self._va_neg_accel_spin = ttk.Spinbox(
            self._va_left, textvariable=self._va_neg_accel_var,
            from_=0.0, to=100.0, increment=0.1, width=10)
        self._va_neg_accel_spin.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._va_neg_accel_spin.config(state="disabled")
        self._va_neg_accel_enable_var.trace_add(
            "write", self._on_va_neg_accel_toggled)
        self._va_neg_accel_var.trace_add(
            "write", self._on_field_changed_trace)
        _WidgetTooltip(self._va_neg_accel_check, TIP_VA_NEG_ACCEL)
        _WidgetTooltip(self._va_neg_accel_spin, TIP_VA_NEG_ACCEL)

        self._va_left.columnconfigure(1, weight=1)

        # --- Right column: trigger mode + analog shaping ---
        row = 0
        self._va_trigger_label = ttk.Label(
            self._va_right, text="Trigger Mode:")
        self._va_trigger_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._va_trigger_var = tk.StringVar()
        self._va_trigger_combo = ttk.Combobox(
            self._va_right, textvariable=self._va_trigger_var,
            values=[m.value for m in ANALOG_EVENT_TRIGGER_MODES],
            state="readonly", width=12)
        self._va_trigger_combo.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._va_trigger_var.trace_add(
            "write", self._on_field_changed_trace)

        row += 1
        self._va_deadband_label = ttk.Label(
            self._va_right, text="Deadband:")
        self._va_deadband_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._va_deadband_var = tk.StringVar(value="0.0")
        self._va_deadband_spin = ttk.Spinbox(
            self._va_right, textvariable=self._va_deadband_var,
            from_=0.0, to=1.0, increment=0.01, width=10)
        self._va_deadband_spin.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._va_deadband_var.trace_add(
            "write", self._on_field_changed_trace)
        _WidgetTooltip(self._va_deadband_label, TIP_DEADBAND)
        _WidgetTooltip(self._va_deadband_spin, TIP_DEADBAND)

        row += 1
        self._va_scale_label = ttk.Label(self._va_right, text="Scale:")
        self._va_scale_label.grid(row=row, column=0, sticky=tk.W, pady=2)
        self._va_scale_var = tk.StringVar(value="1.0")
        self._va_scale_spin = ttk.Spinbox(
            self._va_right, textvariable=self._va_scale_var,
            from_=-10.0, to=10.0, increment=0.1, width=10)
        self._va_scale_spin.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self._va_scale_var.trace_add(
            "write", self._on_field_changed_trace)
        _WidgetTooltip(self._va_scale_label, TIP_SCALE)
        _WidgetTooltip(self._va_scale_spin, TIP_SCALE)

        self._va_right.columnconfigure(1, weight=1)

    def _on_va_neg_ramp_toggled(self, *args):
        """Enable/disable the VA negative ramp rate spinbox."""
        enabled = self._va_neg_ramp_enable_var.get()
        self._va_neg_ramp_spin.config(
            state="normal" if enabled else "disabled")
        if not self._updating_form:
            self._on_field_changed_trace()

    def _on_va_neg_accel_toggled(self, *args):
        """Enable/disable the VA negative acceleration spinbox."""
        enabled = self._va_neg_accel_enable_var.get()
        self._va_neg_accel_spin.config(
            state="normal" if enabled else "disabled")
        if not self._updating_form:
            self._on_field_changed_trace()

    # --- Lower Section Placeholders ---

    def _build_lower_section(self, parent):
        from .curve_editor_widget import CurveEditorWidget

        self._lower_paned = tk.PanedWindow(
            parent, orient=tk.HORIZONTAL, sashwidth=5, sashrelief=tk.RAISED)
        lower_paned = self._lower_paned
        lower_paned.pack(fill=tk.BOTH, expand=True)

        # Left: Curve Editor
        curve_frame = ttk.LabelFrame(
            lower_paned, text="Curve Editor", padding=4)
        lower_paned.add(curve_frame, minsize=120)

        self._curve_editor = CurveEditorWidget(
            curve_frame,
            on_before_change=self._on_before_change,
            on_curve_changed=self._on_curve_changed,
            get_other_curves=self._get_other_curves,
            get_advanced_flags=self._get_advanced_flags,
        )
        self._curve_editor.pack(fill=tk.BOTH, expand=True)

        # Right: Preview widget
        preview_frame = ttk.LabelFrame(
            lower_paned, text="Preview", padding=4)
        lower_paned.add(preview_frame, minsize=120)

        self._preview = PreviewWidget(preview_frame)
        self._preview.pack(fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_advanced_changed(self):
        """Refresh UI elements affected by Advanced menu toggles."""
        if self._action and self._action.input_type == InputType.ANALOG:
            self._update_analog_trigger_values()
        # Refresh curve editor toolbar (monotonic gate)
        self._curve_editor.on_advanced_changed()

    def load_action(self, action: ActionDefinition, qname: str):
        """Populate all panes from the selected action."""
        self._action = action
        self._qname = qname
        self._set_all_enabled(True)

        self._updating_form = True
        try:
            self._name_var.set(action.name)
            # Populate group dropdown with all known groups
            if self._get_group_names:
                self._group_combo['values'] = self._get_group_names()
            elif self._get_all_actions:
                groups = sorted({a.group
                                 for a in self._get_all_actions().values()})
                self._group_combo['values'] = groups
            self._group_var.set(action.group)
            self._desc_text.delete("1.0", tk.END)
            self._desc_text.insert("1.0", action.description)
            self._desc_text.edit_modified(False)
            self._input_type_var.set(action.input_type.value)

            # Trigger mode into the correct pane
            if action.input_type in (InputType.BUTTON,
                                     InputType.BOOLEAN_TRIGGER):
                self._btn_trigger_var.set(action.trigger_mode.value)
            elif action.input_type == InputType.VIRTUAL_ANALOG:
                self._va_trigger_var.set(action.trigger_mode.value)
            else:
                self._analog_trigger_var.set(action.trigger_mode.value)

            # Threshold (BOOLEAN_TRIGGER)
            self._threshold_var.set(str(action.threshold))

            # Analog fields
            self._deadband_var.set(str(action.deadband))
            self._inversion_var.set(action.inversion)
            self._scale_var.set(str(action.scale))
            self._slew_var.set(str(action.slew_rate))
            neg_slew = action.extra.get(EXTRA_NEGATIVE_SLEW_RATE)
            if neg_slew is not None:
                self._neg_slew_enable_var.set(True)
                self._neg_slew_var.set(str(min(float(neg_slew), 0.0)))
            else:
                self._neg_slew_enable_var.set(False)
                self._neg_slew_var.set("0.0")

            # Virtual Analog fields
            self._va_mode_var.set(
                action.extra.get(EXTRA_VA_BUTTON_MODE, "held"))
            self._va_ramp_var.set(
                str(action.extra.get(EXTRA_VA_RAMP_RATE, 0.0)))
            self._va_accel_var.set(
                str(action.extra.get(EXTRA_VA_ACCELERATION, 0.0)))
            self._va_target_var.set(
                str(action.extra.get(EXTRA_VA_TARGET_VALUE, 1.0)))
            self._va_rest_var.set(
                str(action.extra.get(EXTRA_VA_REST_VALUE, 0.0)))
            self._va_zero_vel_var.set(
                bool(action.extra.get(EXTRA_VA_ZERO_VEL_ON_RELEASE, False)))
            neg_ramp = action.extra.get(EXTRA_VA_NEGATIVE_RAMP_RATE)
            if neg_ramp is not None:
                self._va_neg_ramp_enable_var.set(True)
                self._va_neg_ramp_var.set(str(float(neg_ramp)))
            else:
                self._va_neg_ramp_enable_var.set(False)
                self._va_neg_ramp_var.set("0.0")
            neg_accel = action.extra.get(EXTRA_VA_NEGATIVE_ACCELERATION)
            if neg_accel is not None:
                self._va_neg_accel_enable_var.set(True)
                self._va_neg_accel_var.set(str(float(neg_accel)))
            else:
                self._va_neg_accel_enable_var.set(False)
                self._va_neg_accel_var.set("0.0")
            # VA pane deadband/scale mirror main action fields
            self._va_deadband_var.set(str(action.deadband))
            self._va_scale_var.set(str(action.scale))

            self._update_pane_states()
        finally:
            self._updating_form = False

        self._refresh_bindings()
        self._curve_editor.load_action(
            action, qname, self._get_bound_input_names())
        self._preview.load_action(
            action, qname, self._get_bound_input_names(),
            binding_details=self._get_binding_details(),
            paired_action_info=self._find_paired_analog_action())

    def clear(self):
        """Clear all panes (no action selected)."""
        self._action = None
        self._qname = None

        self._updating_form = True
        try:
            self._name_var.set("")
            self._group_var.set("")
            self._desc_text.delete("1.0", tk.END)
            self._desc_text.edit_modified(False)
            self._input_type_var.set("")
            self._btn_trigger_var.set("")
            self._analog_trigger_var.set("")
            self._deadband_var.set("0.0")
            self._inversion_var.set(False)
            self._scale_var.set("1.0")
            self._slew_var.set("0.0")
            self._neg_slew_enable_var.set(False)
            self._neg_slew_var.set("0.0")
            # VA fields
            self._va_trigger_var.set("")
            self._va_mode_var.set("held")
            self._va_ramp_var.set("0.0")
            self._va_accel_var.set("0.0")
            self._va_target_var.set("1.0")
            self._va_rest_var.set("0.0")
            self._va_zero_vel_var.set(False)
            self._va_neg_ramp_enable_var.set(False)
            self._va_neg_ramp_var.set("0.0")
            self._va_neg_accel_enable_var.set(False)
            self._va_neg_accel_var.set("0.0")
            self._va_deadband_var.set("0.0")
            self._va_scale_var.set("1.0")
        finally:
            self._updating_form = False

        self._bound_tree.delete(*self._bound_tree.get_children())
        self._bound_map.clear()
        self._assign_combo.config(values=[])
        self._assign_map.clear()
        self._set_all_enabled(False)
        self._curve_editor.clear()
        self._preview.clear()

    def refresh_bindings(self):
        """Re-query binding info for the current action."""
        self._refresh_bindings()

    # ------------------------------------------------------------------
    # Curve Editor Callbacks
    # ------------------------------------------------------------------

    def _on_curve_changed(self):
        """Called by CurveEditorWidget when curve data is modified."""
        # The curve editor may have changed action.scale (via scale handle
        # drag). Sync the spinbox so _save_to_action won't overwrite it.
        if self._action:
            self._updating_form = True
            try:
                self._scale_var.set(str(self._action.scale))
                self._threshold_var.set(str(self._action.threshold))
            finally:
                self._updating_form = False
        self._preview.refresh()
        if self._on_field_changed:
            self._on_field_changed()

    def _get_other_curves(self, mode: str) -> dict[str, list[dict]]:
        """Return curves from other actions for 'Copy from...'."""
        if not self._get_all_actions:
            return {}
        key = EXTRA_SPLINE_POINTS if mode == "spline" else EXTRA_SEGMENT_POINTS
        all_actions = self._get_all_actions()
        curves = {}
        for qname, action in all_actions.items():
            if qname != self._qname:
                pts = action.extra.get(key)
                if pts:
                    curves[qname] = pts
        return curves

    def _update_curve_editor(self):
        """Refresh the curve editor when action parameters change."""
        if self._action:
            self._curve_editor.load_action(
                self._action, self._qname,
                self._get_bound_input_names())

    # ------------------------------------------------------------------
    # Pane State Management
    # ------------------------------------------------------------------

    def _set_all_enabled(self, enabled: bool):
        """Enable/disable all panes."""
        state = "normal" if enabled else "disabled"
        _set_children_state(self._common_frame, state)
        _set_children_state(self._bindings_frame, state)
        _set_children_state(self._button_frame, state)
        _set_children_state(self._analog_frame, state)
        _set_children_state(self._va_frame, state)
        if not enabled:
            self._show_options_pane(None)

    def _show_options_pane(self, which: str | None):
        """Swap the right pane between 'button', 'analog', 'virtual_analog', or None."""
        if self._active_options == which:
            return
        # Hide current
        if self._active_options == "button":
            self._button_frame.pack_forget()
        elif self._active_options == "analog":
            self._analog_frame.pack_forget()
        elif self._active_options == "virtual_analog":
            self._va_frame.pack_forget()

        # Show new
        self._active_options = which
        if which == "button":
            self._button_frame.pack(fill=tk.BOTH, expand=True)
            self._button_frame.configure(style="Active.TLabelframe")
            _set_children_state(self._button_frame, "normal")
        elif which == "analog":
            self._analog_frame.pack(fill=tk.BOTH, expand=True)
            self._analog_frame.configure(style="Active.TLabelframe")
            _set_children_state(self._analog_frame, "normal")
        elif which == "virtual_analog":
            self._va_frame.pack(fill=tk.BOTH, expand=True)
            self._va_frame.configure(style="Active.TLabelframe")
            _set_children_state(self._va_frame, "normal")

    def _update_pane_states(self):
        """Activate the correct options pane based on input type."""
        if not self._action:
            self._show_options_pane(None)
            return

        itype = self._action.input_type
        is_button = itype in (InputType.BUTTON, InputType.BOOLEAN_TRIGGER)
        is_analog = itype == InputType.ANALOG
        is_va = itype == InputType.VIRTUAL_ANALOG

        if is_button:
            self._show_options_pane("button")
            self._btn_info_label.config(text="")
            # Threshold: enabled for BOOLEAN_TRIGGER, disabled for BUTTON
            thresh_state = ("normal" if itype == InputType.BOOLEAN_TRIGGER
                            else "disabled")
            self._threshold_spin.config(state=thresh_state)
        elif is_analog:
            self._show_options_pane("analog")
            self._update_analog_trigger_values()
            self._update_raw_mode_disable()
            self._on_neg_slew_toggled()
        elif is_va:
            self._show_options_pane("virtual_analog")
            self._on_va_neg_ramp_toggled()
            self._on_va_neg_accel_toggled()
        else:
            # OUTPUT or other — show button pane as placeholder
            self._show_options_pane("button")
            _set_children_state(self._button_frame, "disabled")
            self._button_frame.configure(style="Inactive.TLabelframe")
            self._btn_info_label.config(
                text="No type-specific options\nfor this input type.")

    _SPLINE_ADV_SUFFIX = "  (Advanced)"

    def _update_analog_trigger_values(self):
        """Refresh analog trigger combo values based on advanced flags."""
        flags = self._get_advanced_flags()
        current = self._analog_trigger_var.get()
        values = []
        for m in ANALOG_EVENT_TRIGGER_MODES:
            label = m.value
            if (m == EventTriggerMode.SPLINE and not flags["splines"]
                    and current != EventTriggerMode.SPLINE.value):
                label += self._SPLINE_ADV_SUFFIX
            values.append(label)
        self._analog_trigger_combo['values'] = values

    def _check_spline_gate(self, *args):
        """Revert spline selection if splines are disabled."""
        if self._updating_form:
            return
        val = self._analog_trigger_var.get()
        if val.endswith(self._SPLINE_ADV_SUFFIX):
            self._updating_form = True
            self._analog_trigger_var.set(
                self._action.trigger_mode.value
                if self._action else EventTriggerMode.SCALED.value)
            self._updating_form = False
            messagebox.showinfo(
                "Advanced Feature",
                "Enable splines in Advanced menu to use this mode.")

    def _update_raw_mode_disable(self):
        """Disable axis fields when trigger mode is RAW."""
        if not self._action:
            return
        if self._action.input_type not in (
                InputType.ANALOG, InputType.VIRTUAL_ANALOG):
            return
        trig_var = (self._va_trigger_var
                    if self._action.input_type == InputType.VIRTUAL_ANALOG
                    else self._analog_trigger_var)
        is_raw = trig_var.get() == EventTriggerMode.RAW.value
        state = "disabled" if is_raw else "normal"
        for w in self._axis_widgets:
            try:
                w.config(state=state)
            except tk.TclError:
                pass  # Some widgets don't support the 'state' option
        if not is_raw:
            neg_state = ("normal" if self._neg_slew_enable_var.get()
                         else "disabled")
            self._neg_slew_spin.config(state=neg_state)

    # ------------------------------------------------------------------
    # Binding Management
    # ------------------------------------------------------------------

    def _refresh_bindings(self):
        """Refresh the assigned-inputs treeview and assign dropdown."""
        self._bound_tree.delete(*self._bound_tree.get_children())
        self._bound_map.clear()
        self._binding_icons.clear()
        self._assign_combo.config(values=[])
        self._assign_map.clear()

        if not self._qname:
            return
        if not (self._get_all_controllers and self._get_compatible_inputs
                and self._is_action_bound):
            return

        controllers = self._get_all_controllers()
        all_inputs = self._get_compatible_inputs(self._qname)

        # Populate assigned inputs treeview + bound_map
        for port, ctrl_name in controllers:
            for input_name, display in all_inputs:
                if self._is_action_bound(self._qname, port, input_name):
                    label = f"{ctrl_name}: {display}"
                    icon = None
                    if self._icon_loader:
                        icon = self._icon_loader.get_tk_icon(
                            input_name, 20)
                    kwargs = {}
                    if icon:
                        self._binding_icons.append(icon)
                        kwargs["image"] = icon
                    self._bound_tree.insert(
                        "", tk.END, text=label, **kwargs)
                    self._bound_map[label] = (port, input_name)

        # Populate assign dropdown with compatible unbound inputs
        options = []
        for port, ctrl_name in controllers:
            for input_name, display in all_inputs:
                if not self._is_action_bound(
                        self._qname, port, input_name):
                    label = f"{ctrl_name}: {display}"
                    options.append(label)
                    self._assign_map[label] = (port, input_name)
        self._assign_combo.config(values=options)
        if options:
            self._assign_var.set(options[0])
        else:
            self._assign_var.set("")

    def _get_bound_input_names(self) -> list[str]:
        """Return list of input names currently bound to this action."""
        return [inp for _, inp in self._bound_map.values()]

    def _get_binding_details(self) -> list[tuple[int, str]]:
        """Return list of (port, input_name) for current action bindings."""
        return list(self._bound_map.values())

    def _find_paired_analog_action(self) -> tuple | None:
        """Find the paired stick-axis action for 2D preview overlay.

        Returns (ActionDefinition, qname) if a paired analog action
        exists, else None.
        """
        if not self._bound_map or not self._get_all_actions:
            return None
        # Find first stick binding
        primary_port = None
        paired_input = None
        for _label, (port, input_name) in self._bound_map.items():
            paired = STICK_PAIRS.get(input_name)
            if paired:
                primary_port = port
                paired_input = paired
                break
        if not paired_input:
            return None
        # Search all actions for one bound to paired_input on same port
        all_actions = self._get_all_actions()
        for qname, action in all_actions.items():
            if qname == self._qname:
                continue
            if (action.input_type == InputType.ANALOG
                    and self._is_action_bound
                    and self._is_action_bound(
                        qname, primary_port, paired_input)):
                return (action, qname)
        return None

    def _on_assign(self):
        """Assign the selected input to the current action."""
        if not self._qname:
            return
        label = self._assign_var.get()
        mapping = self._assign_map.get(label)
        if not mapping:
            return
        port, input_name = mapping
        if self._on_before_change:
            self._on_before_change(0)
        if self._on_assign_action:
            self._on_assign_action(self._qname, port, input_name)
        self._refresh_bindings()
        bound = self._get_bound_input_names()
        self._curve_editor.update_bindings(bound)
        self._preview.update_bindings(
            bound,
            binding_details=self._get_binding_details(),
            paired_action_info=self._find_paired_analog_action())
        if self._on_field_changed:
            self._on_field_changed()

    def _on_unassign(self):
        """Remove the selected binding from the current action."""
        if not self._qname:
            return
        sel = self._bound_tree.selection()
        if not sel:
            return
        label = self._bound_tree.item(sel[0], "text")
        mapping = self._bound_map.get(label)
        if not mapping:
            return
        port, input_name = mapping
        if self._on_before_change:
            self._on_before_change(0)
        if self._on_unassign_action:
            self._on_unassign_action(self._qname, port, input_name)
        self._refresh_bindings()
        bound = self._get_bound_input_names()
        self._curve_editor.update_bindings(bound)
        self._preview.update_bindings(
            bound,
            binding_details=self._get_binding_details(),
            paired_action_info=self._find_paired_analog_action())
        if self._on_field_changed:
            self._on_field_changed()

    # ------------------------------------------------------------------
    # Field Change Handlers
    # ------------------------------------------------------------------

    def _on_field_changed_trace(self, *args):
        """Trace callback for variable writes."""
        if self._updating_form or not self._action:
            return
        self._save_to_action()
        # Refresh spline gate after trigger mode change
        if self._action and self._action.input_type == InputType.ANALOG:
            self._update_analog_trigger_values()
        self._update_curve_editor()
        self._preview.refresh()
        if self._on_field_changed:
            self._on_field_changed()

    def _set_field_error(self, widget, has_error: bool):
        """Apply or clear error styling on a ttk Entry or Combobox."""
        base = widget.winfo_class()
        widget.configure(style=f"Error.{base}" if has_error else f"{base}")

    def _flash_field_warning(self, widget, err: str):
        """Flash error styling and show a warning for an invalid field."""
        if getattr(self, '_showing_warning', False):
            return
        self._showing_warning = True
        self._set_field_error(widget, True)
        messagebox.showwarning("Invalid Value", err)
        self._set_field_error(widget, False)
        self._showing_warning = False

    def _commit_name_group(self, event=None):
        """Commit name/group changes on focus-out or Enter."""
        if self._updating_form or not self._action:
            return

        action = self._action
        new_name = self._name_var.get().strip()
        new_group = self._group_var.get().strip()
        changed = False

        # Validate and apply name
        if new_name and new_name != action.name:
            err = validate_action_name(new_name)
            if err:
                self._flash_field_warning(self._name_entry, err)
                self._updating_form = True
                self._name_var.set(action.name)
                self._updating_form = False
            else:
                action.name = new_name
                changed = True
        elif not new_name:
            self._flash_field_warning(
                self._name_entry, "Name cannot be empty.")
            self._updating_form = True
            self._name_var.set(action.name)
            self._updating_form = False
        self._set_field_error(self._name_entry, False)

        # Validate and apply group
        if new_group and new_group != action.group:
            err = validate_action_group(new_group)
            if err:
                self._flash_field_warning(self._group_combo, err)
                self._updating_form = True
                self._group_var.set(action.group)
                self._updating_form = False
            else:
                action.group = new_group
                changed = True
        elif not new_group:
            self._flash_field_warning(
                self._group_combo, "Group cannot be empty.")
            self._updating_form = True
            self._group_var.set(action.group)
            self._updating_form = False
        self._set_field_error(self._group_combo, False)

        if changed and self._on_field_changed:
            self._on_field_changed()

    def _on_desc_modified(self, event=None):
        """Handle description Text widget changes."""
        if not self._desc_text.edit_modified():
            return
        self._desc_text.edit_modified(False)
        if self._updating_form or not self._action:
            return
        self._save_to_action()
        if self._on_field_changed:
            self._on_field_changed()

    def _on_input_type_changed_trace(self, *args):
        """Handle input type changes with warning and pane switching."""
        if self._updating_form or not self._action:
            return

        new_type_str = self._input_type_var.get()
        if not new_type_str:
            return
        try:
            new_type = InputType(new_type_str)
        except ValueError:
            return

        if new_type == self._action.input_type:
            return

        # Warn if action has custom settings
        if getattr(self._action, '_has_custom', False):
            if not messagebox.askyesno(
                "Change Input Type",
                "Changing input type may reset or\n"
                "invalidate current settings (deadband,\n"
                "scale, curves, bindings). Continue?",
            ):
                # Defer revert — setting a var inside its own trace is unreliable
                old_val = self._action.input_type.value
                self.after_idle(self._revert_input_type, old_val)
                return

        if self._on_before_change:
            self._on_before_change(0)

        self._type_switch_active = True
        try:
            self._action.input_type = new_type

            if new_type == InputType.ANALOG:
                if self._action.trigger_mode in BUTTON_EVENT_TRIGGER_MODES:
                    self._action.trigger_mode = EventTriggerMode.SCALED
                if self._action.deadband < 0.01:
                    self._action.deadband = 0.05
            elif new_type in (InputType.BUTTON, InputType.BOOLEAN_TRIGGER):
                if self._action.trigger_mode in ANALOG_EVENT_TRIGGER_MODES:
                    self._action.trigger_mode = EventTriggerMode.ON_TRUE

            self.load_action(self._action, self._qname)
        finally:
            self._type_switch_active = False

        self._action._has_custom = False
        if self._on_field_changed:
            self._on_field_changed()

    def _revert_input_type(self, old_val):
        """Revert the input type radio after user cancelled type switch."""
        self._updating_form = True
        try:
            self._input_type_var.set(old_val)
        finally:
            self._updating_form = False

    def _on_neg_slew_toggled(self, *args):
        """Enable/disable the negative slew rate spinbox."""
        if self._action and self._action.input_type == InputType.ANALOG:
            is_raw = (self._analog_trigger_var.get()
                      == EventTriggerMode.RAW.value)
            if not is_raw:
                enabled = self._neg_slew_enable_var.get()
                self._neg_slew_spin.config(
                    state="normal" if enabled else "disabled")
        if not self._updating_form:
            self._on_field_changed_trace()

    def _save_to_action(self):
        """Write current form values back to the ActionDefinition."""
        action = self._action
        if not action:
            return

        if self._on_before_change:
            self._on_before_change(200)

        action.description = self._desc_text.get("1.0", "end-1c").strip()
        # Name and group are committed on focus-out/Enter, not on every
        # keystroke — see _commit_name_group().

        # Trigger mode from the active pane
        if action.input_type in (InputType.BUTTON,
                                 InputType.BOOLEAN_TRIGGER):
            trigger_str = self._btn_trigger_var.get()
        elif action.input_type == InputType.VIRTUAL_ANALOG:
            trigger_str = self._va_trigger_var.get()
        else:
            trigger_str = self._analog_trigger_var.get()
        # Strip the "(Advanced)" suffix if present (user should not be able
        # to select it, but guard against it).
        if trigger_str and trigger_str.endswith(self._SPLINE_ADV_SUFFIX):
            trigger_str = ""
        if trigger_str:
            try:
                action.trigger_mode = EventTriggerMode(trigger_str)
            except ValueError:
                pass  # Invalid trigger mode string; keep previous value

        # Threshold (BOOLEAN_TRIGGER)
        if action.input_type == InputType.BOOLEAN_TRIGGER:
            try:
                action.threshold = float(
                    self._threshold_var.get() or 0.5)
            except ValueError:
                pass  # Invalid input; keep previous threshold

        # Analog fields
        try:
            action.deadband = float(self._deadband_var.get() or 0.0)
        except ValueError:
            pass  # Invalid input; keep previous deadband value
        action.inversion = self._inversion_var.get()
        try:
            action.scale = float(self._scale_var.get() or 1.0)
        except ValueError:
            pass  # Invalid input; keep previous scale value
        try:
            action.slew_rate = float(self._slew_var.get() or 0.0)
        except ValueError:
            pass  # Invalid input; keep previous slew rate value

        if self._neg_slew_enable_var.get():
            try:
                val = float(self._neg_slew_var.get() or 0.0)
                action.extra[EXTRA_NEGATIVE_SLEW_RATE] = min(val, 0.0)
            except ValueError:
                pass  # Invalid input; keep previous negative slew value
        else:
            action.extra.pop(EXTRA_NEGATIVE_SLEW_RATE, None)

        # Virtual Analog extra fields
        if action.input_type == InputType.VIRTUAL_ANALOG:
            try:
                action.extra[EXTRA_VA_BUTTON_MODE] = (
                    self._va_mode_var.get() or "held")
                action.extra[EXTRA_VA_RAMP_RATE] = float(
                    self._va_ramp_var.get() or 0.0)
                action.extra[EXTRA_VA_ACCELERATION] = float(
                    self._va_accel_var.get() or 0.0)
                action.extra[EXTRA_VA_TARGET_VALUE] = float(
                    self._va_target_var.get() or 1.0)
                action.extra[EXTRA_VA_REST_VALUE] = float(
                    self._va_rest_var.get() or 0.0)
                action.extra[EXTRA_VA_ZERO_VEL_ON_RELEASE] = bool(
                    self._va_zero_vel_var.get())
                if self._va_neg_ramp_enable_var.get():
                    action.extra[EXTRA_VA_NEGATIVE_RAMP_RATE] = float(
                        self._va_neg_ramp_var.get() or 0.0)
                else:
                    action.extra.pop(EXTRA_VA_NEGATIVE_RAMP_RATE, None)
                if self._va_neg_accel_enable_var.get():
                    action.extra[EXTRA_VA_NEGATIVE_ACCELERATION] = float(
                        self._va_neg_accel_var.get() or 0.0)
                else:
                    action.extra.pop(EXTRA_VA_NEGATIVE_ACCELERATION, None)
                # VA pane has its own deadband/scale spinboxes
                action.deadband = float(
                    self._va_deadband_var.get() or 0.0)
                action.scale = float(
                    self._va_scale_var.get() or 1.0)
            except ValueError:
                pass

        if not self._type_switch_active:
            action._has_custom = True

        self._update_raw_mode_disable()
