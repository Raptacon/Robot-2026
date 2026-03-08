"""Gamepad input via XInput for the preview widget.

Wraps the XInput-Python library with graceful fallback when not installed.
Maps XInput axis names to wpilib controller input names.
"""


class GamepadPoller:
    """Poll Xbox controllers via XInput with graceful fallback.

    If XInput-Python is not installed, ``available`` returns False and
    all query methods return empty/zero values.
    """

    # Map wpilib input names → (source, index/key)
    # source: "thumb" or "trigger"
    # For thumbs: index 0=left, 1=right; sub 0=X, 1=Y
    # For triggers: 0=left, 1=right
    # Y-axis negated to match wpilib convention: getLeftY()/getRightY()
    # return negative when pushed forward/up.
    _AXIS_MAP = {
        "left_stick_x":  ("thumb", 0, 0, False),
        "left_stick_y":  ("thumb", 0, 1, True),   # negate: wpilib Y-forward = negative
        "right_stick_x": ("thumb", 1, 0, False),
        "right_stick_y": ("thumb", 1, 1, True),   # negate: wpilib Y-forward = negative
        "left_trigger":  ("trigger", 0, None, False),
        "right_trigger": ("trigger", 1, None, False),
    }

    def __init__(self):
        self._xinput = None
        try:
            import XInput
            self._xinput = XInput
            # Disable XInput's built-in deadzones — our pipeline handles
            # deadband, so we want raw values.
            XInput.set_deadzone(XInput.DEADZONE_LEFT_THUMB, 0)
            XInput.set_deadzone(XInput.DEADZONE_RIGHT_THUMB, 0)
            XInput.set_deadzone(XInput.DEADZONE_TRIGGER, 0)
        except (ImportError, OSError):
            pass  # XInput unavailable; self._xinput stays None, fallback to no gamepad

    @property
    def available(self) -> bool:
        """True if XInput-Python is installed and usable."""
        return self._xinput is not None

    def get_connected(self) -> list[int]:
        """Return indices of connected controllers (0-3)."""
        if not self._xinput:
            return []
        try:
            flags = self._xinput.get_connected()
            return [i for i, ok in enumerate(flags) if ok]
        except Exception:
            return []

    def get_axis(self, controller_id: int, axis_name: str) -> float:
        """Read a single axis by wpilib input name.

        Returns 0.0 if controller is disconnected or axis_name unknown.
        Stick axes return -1..1, trigger axes return 0..1.
        Stick Y axes are negated to match wpilib (forward = negative).
        """
        mapping = self._AXIS_MAP.get(axis_name)
        if not mapping or not self._xinput:
            return 0.0
        source, idx, sub, negate = mapping
        try:
            state = self._xinput.get_state(controller_id)
        except Exception:
            return 0.0
        if source == "thumb":
            thumbs = self._xinput.get_thumb_values(state)
            val = thumbs[idx][sub]
            return -val if negate else val
        else:
            triggers = self._xinput.get_trigger_values(state)
            return triggers[idx]

    def get_all_axes(self, controller_id: int) -> dict[str, float]:
        """Return all 6 axis values for a controller.

        Keys are wpilib input names. Returns empty dict on error.
        """
        if not self._xinput:
            return {}
        try:
            state = self._xinput.get_state(controller_id)
        except Exception:
            return {}
        thumbs = self._xinput.get_thumb_values(state)
        triggers = self._xinput.get_trigger_values(state)
        return {
            "left_stick_x": thumbs[0][0],
            "left_stick_y": -thumbs[0][1],
            "right_stick_x": thumbs[1][0],
            "right_stick_y": -thumbs[1][1],
            "left_trigger": triggers[0],
            "right_trigger": triggers[1],
        }
