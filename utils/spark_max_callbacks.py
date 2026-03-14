# Third-party imports
import rev


class SparkMaxCallbacks:
    """
    Wraps a REV SparkMax motor and encoder into a dict of callbacks
    for PositionCalibration.

    You usually don't need to use this class directly. Pass
    ``motor=`` to PositionCalibration and it creates these
    callbacks for you automatically.

    Direct usage (if you want to customize one callback)::

        # Start from SparkMax defaults, then override one
        cbs = SparkMaxCallbacks(motor, encoder).as_dict()
        cbs['on_limit_detected'] = my_custom_handler
        cal = PositionCalibration(name="Turret", ..., **cbs)

    Returned callbacks and what they wrap:

    ============================  ======================================
    Callback name                 SparkMax call
    ============================  ======================================
    ``set_motor_output``          ``motor.set(pct)``
    ``stop_motor``                ``motor.stopMotor()``
    ``set_position``              ``encoder.setPosition(value)``
    ``get_position``              ``encoder.getPosition()``
    ``get_velocity``              ``encoder.getVelocity()``
    ``get_forward_limit_switch``  ``motor.getForwardLimitSwitch().get()``
    ``get_reverse_limit_switch``  ``motor.getReverseLimitSwitch().get()``
    ``set_current_limit``         ``motor.configure(smartCurrentLimit)``
    ``set_soft_limits``           ``motor.configure(softLimit ...)``
    ``disable_soft_limits``       ``motor.configure(softLimit ...)``
    ``save_config``               reads ``motor.configAccessor``
    ``restore_config``            ``motor.configure(...)``
    ``set_conversion_factor``     ``motor.configure(encoder ...)``
    ============================  ======================================
    """

    def __init__(self, motor: rev.SparkMax, encoder=None):
        self._motor = motor
        self._encoder = encoder or motor.getEncoder()

    def as_dict(self) -> dict:
        """Return all callbacks as a dict for PositionCalibration(**kwargs)."""
        return {
            'get_position': lambda: self._encoder.getPosition(),
            'get_velocity': lambda: self._encoder.getVelocity(),
            'set_position': lambda v: self._encoder.setPosition(v),
            'set_motor_output': lambda p: self._motor.set(p),
            'stop_motor': lambda: self._motor.stopMotor(),
            'set_current_limit': self._make_set_current_limit(),
            'set_soft_limits': self._make_set_soft_limits(),
            'disable_soft_limits': self._make_disable_soft_limits(),
            'save_config': self._make_save_config(),
            'restore_config': self._make_restore_config(),
            'get_forward_limit_switch': (
                lambda: self._motor.getForwardLimitSwitch().get()
            ),
            'get_reverse_limit_switch': (
                lambda: self._motor.getReverseLimitSwitch().get()
            ),
            'set_conversion_factor': (
                self._make_set_conversion_factor()
            ),
        }

    def _make_set_current_limit(self):
        motor = self._motor

        def set_current_limit(amps):
            cfg = rev.SparkMaxConfig()
            cfg.smartCurrentLimit(int(amps))
            motor.configure(
                cfg,
                rev.ResetMode.kNoResetSafeParameters,
                rev.PersistMode.kNoPersistParameters
            )
        return set_current_limit

    def _make_set_soft_limits(self):
        motor = self._motor

        def set_soft_limits(min_limit, max_limit):
            cfg = rev.SparkMaxConfig()
            (
                cfg.softLimit
                .forwardSoftLimit(max_limit)
                .forwardSoftLimitEnabled(True)
                .reverseSoftLimit(min_limit)
                .reverseSoftLimitEnabled(True)
            )
            motor.configure(
                cfg,
                rev.ResetMode.kNoResetSafeParameters,
                rev.PersistMode.kNoPersistParameters
            )
        return set_soft_limits

    def _make_disable_soft_limits(self):
        motor = self._motor

        def disable_soft_limits(forward, reverse):
            cfg = rev.SparkMaxConfig()
            if forward:
                cfg.softLimit.forwardSoftLimitEnabled(False)
            if reverse:
                cfg.softLimit.reverseSoftLimitEnabled(False)
            motor.configure(
                cfg,
                rev.ResetMode.kNoResetSafeParameters,
                rev.PersistMode.kNoPersistParameters
            )
        return disable_soft_limits

    def _make_save_config(self):
        motor = self._motor

        def save_config():
            ca = motor.configAccessor
            return {
                'current_limit': ca.getSmartCurrentLimit(),
                'current_free_limit': ca.getSmartCurrentFreeLimit(),
                'current_rpm_limit': ca.getSmartCurrentRPMLimit(),
                'fwd_soft_limit_enabled': (
                    ca.softLimit.getForwardSoftLimitEnabled()
                ),
                'rev_soft_limit_enabled': (
                    ca.softLimit.getReverseSoftLimitEnabled()
                ),
                'fwd_soft_limit': ca.softLimit.getForwardSoftLimit(),
                'rev_soft_limit': ca.softLimit.getReverseSoftLimit(),
            }
        return save_config

    def _make_restore_config(self):
        motor = self._motor

        def restore_config(saved):
            cfg = rev.SparkMaxConfig()
            cfg.smartCurrentLimit(
                int(saved['current_limit']),
                int(saved['current_free_limit']),
                int(saved['current_rpm_limit'])
            )
            (
                cfg.softLimit
                .forwardSoftLimitEnabled(saved['fwd_soft_limit_enabled'])
                .reverseSoftLimitEnabled(saved['rev_soft_limit_enabled'])
            )
            motor.configure(
                cfg,
                rev.ResetMode.kNoResetSafeParameters,
                rev.PersistMode.kNoPersistParameters
            )
        return restore_config

    def _make_set_conversion_factor(self):
        motor = self._motor

        def set_conversion_factor(factor):
            velocity_factor = factor / 60.0
            cfg = rev.SparkMaxConfig()
            (
                cfg.encoder
                .positionConversionFactor(factor)
                .velocityConversionFactor(velocity_factor)
            )
            motor.configure(
                cfg,
                rev.ResetMode.kNoResetSafeParameters,
                rev.PersistMode.kNoPersistParameters
            )
        return set_conversion_factor
