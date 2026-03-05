"""Shared tooltip strings for the controller config GUI.

Both ActionPanel (sidebar) and ActionEditorTab reference these so
that the same field always shows the same help text.
"""

# ---------------------------------------------------------------------------
#   Action identity fields
# ---------------------------------------------------------------------------

TIP_NAME = ("Short action name (no dots). Combined\n"
            "with group to form qualified name: group.name")

TIP_GROUP = ("Group this action belongs to.\n"
             "Type a new name to create a group.")

TIP_DESC = ("Human-readable description of\n"
            "what this action does on the robot.")

TIP_INPUT_TYPE = ("Input type determines available options:\n"
                  "  button — digital on/off (incl. D-pad)\n"
                  "  analog — continuous value (stick, trigger)\n"
                  "  boolean trigger — axis threshold to on/off\n"
                  "  output — rumble or LED feedback")

# ---------------------------------------------------------------------------
#   Trigger mode
# ---------------------------------------------------------------------------

# Combined tooltip (sidebar uses one combo for both button + analog modes)
TIP_TRIGGER = ("Button modes — when the command fires:\n"
               "  on_true — runs while input is pressed\n"
               "  on_false — runs while input is released\n"
               "  while_true — starts on press, ends on release\n"
               "  while_false — starts on release, ends on press\n"
               "  toggle_on_true — toggles on/off each press\n"
               "\n"
               "Analog modes — how the input is shaped:\n"
               "  raw — no processing, bypasses all shaping\n"
               "  scaled — linear output multiplied by scale\n"
               "  squared — quadratic curve for fine control\n"
               "  spline — custom cubic hermite curve\n"
               "  segmented — custom piecewise-linear curve")

# Expanded tooltips (action editor has separate panes)
TIP_TRIGGER_BUTTON = ("When the button command fires:\n"
                      "  on_true — runs while input is pressed\n"
                      "  on_false — runs while input is released\n"
                      "  while_true — starts on press, ends on release\n"
                      "  while_false — starts on release, ends on press\n"
                      "  toggle_on_true — toggles on/off each press")

TIP_TRIGGER_ANALOG = ("How the analog input value is shaped:\n"
                      "  raw — no processing, bypasses all shaping\n"
                      "  scaled — linear output multiplied by scale\n"
                      "  squared — quadratic curve for fine control\n"
                      "  spline — custom cubic hermite curve\n"
                      "  segmented — custom piecewise-linear curve")

# ---------------------------------------------------------------------------
#   Analog shaping fields
# ---------------------------------------------------------------------------

TIP_DEADBAND = ("Dead zone around center (0.0–1.0).\n"
                "Input below this threshold reads as 0.\n"
                "Prevents drift from stick center.")

TIP_INVERSION = ("Negate the input value.\n"
                 "Flips the axis direction.")

TIP_SCALE = ("Multiplier applied to the output value.\n"
             "Use to limit max speed or amplify input.")

TIP_SLEW = ("Max rate of output change per second.\n"
            "0 = disabled (no slew limiting).\n"
            "Smooths sudden input changes.")

TIP_NEG_SLEW = ("Separate slew rate for decreasing values.\n"
                "Enables asymmetric acceleration/braking.\n"
                "Must be negative or zero.")

TIP_THRESHOLD = ("Axis value threshold for boolean conversion.\n"
                 "Input above this value reads as True.\n"
                 "Range: 0.0 to 1.0 (default 0.5).")

# ---------------------------------------------------------------------------
#   Curve editor buttons (sidebar)
# ---------------------------------------------------------------------------

TIP_EDIT_SPLINE = ("Open the visual spline curve editor.\n"
                   "Click to add points, right-click to remove.")

TIP_EDIT_SEGMENTS = ("Open the piecewise-linear curve editor.\n"
                     "Click to add points, right-click to remove.")

# ---------------------------------------------------------------------------
#   Bindings pane (action editor)
# ---------------------------------------------------------------------------

TIP_ASSIGN_INPUT = ("Select a controller input and click +\n"
                    "to bind it to this action.")

TIP_ASSIGN_BTN = "Assign selected input to this action"

TIP_BOUND_LIST = ("Currently assigned inputs.\n"
                  "Double-click to remove a binding.")

TIP_UNASSIGN_BTN = "Remove the selected binding"

# ---------------------------------------------------------------------------
#   Filter bar (sidebar)
# ---------------------------------------------------------------------------

TIP_FILTER = ("Filter by name, group, or description.\n"
              "Wildcards: * = any chars, ? = one char.\n"
              "e.g. r*n = starts with r ends with n,\n"
              "*ee* = contains ee. Escape to clear.")

TIP_FILTER_UNASSIGNED = ("Show only actions not assigned\n"
                         "to any controller input.")

TIP_FILTER_MULTI = ("Show only actions bound to\n"
                    "more than one input.")
