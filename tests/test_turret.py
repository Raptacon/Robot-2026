"""
Unit tests for the Turret subsystem.

Tests validate:
- Motor output behavior for voltage and position control commands
- Simulated encoder position and velocity feedback
- Soft limit configuration
- Encoder conversion factor configuration
- Homing routine via calibration controller: init, periodic stall detection,
  timeout, cleanup
- Calibration routine via calibration controller: full sequence, single
  direction with known range, abort and restore
- Periodic position tracking and turretDisable idle state
"""

# Native imports
import unittest

# Third-party imports
import rev
import wpilib.simulation
from wpimath.system.plant import DCMotor

# Internal imports
from subsystem.mechanisms.turret import Turret


class TestTurret(unittest.TestCase):
    """Test suite for the Turret subsystem.

    Uses setUpClass/tearDownClass to create a single SparkMax instance
    shared across all tests, since REV enforces one instance per CAN ID.
    """

    # Test constants
    MOTOR_CAN_ID = 40
    # Example: a 100:1 gear ratio turret
    # 1 motor rotation = 360/100 = 3.6 degrees of turret rotation
    POSITION_CONVERSION_FACTOR = 3.6  # degrees per motor rotation
    MIN_SOFT_LIMIT = -90.0  # degrees
    MAX_SOFT_LIMIT = 90.0   # degrees

    @classmethod
    def setUpClass(cls):
        """Create motor, turret, and simulation objects once for all tests."""
        wpilib.simulation.pauseTiming()
        cls.motor = rev.SparkMax(
            cls.MOTOR_CAN_ID,
            rev.SparkLowLevel.MotorType.kBrushless
        )
        cls.turret = Turret(
            motor=cls.motor,
            position_conversion_factor=cls.POSITION_CONVERSION_FACTOR,
            min_soft_limit=cls.MIN_SOFT_LIMIT,
            max_soft_limit=cls.MAX_SOFT_LIMIT
        )
        cls.motor_sim = rev.SparkSim(cls.motor, DCMotor.NEO())
        cls.motor_sim.setBusVoltage(12.0)

    def setUp(self):
        """Reset motor and turret state before each test."""
        # Abort any active calibration or homing
        self.turret.calibration.abort()
        # Reset calibration state for clean tests
        self.turret.calibration._is_calibrated = False
        self.turret.calibration._is_calibrating = False
        self.turret.calibration._calibration_phase = 0
        self.turret.calibration._is_homing = False
        self.turret.calibration._hard_limit_min = None
        self.turret.calibration._hard_limit_max = None

        # Restore soft limits to test defaults
        self.turret.calibration._min_soft_limit = self.MIN_SOFT_LIMIT
        self.turret.calibration._max_soft_limit = self.MAX_SOFT_LIMIT
        self.turret.min_soft_limit = self.MIN_SOFT_LIMIT
        self.turret.max_soft_limit = self.MAX_SOFT_LIMIT
        limit_config = rev.SparkMaxConfig()
        (
            limit_config.softLimit
            .forwardSoftLimit(self.MAX_SOFT_LIMIT)
            .forwardSoftLimitEnabled(True)
            .reverseSoftLimit(self.MIN_SOFT_LIMIT)
            .reverseSoftLimitEnabled(True)
        )
        self.motor.configure(
            limit_config,
            rev.ResetMode.kNoResetSafeParameters,
            rev.PersistMode.kNoPersistParameters
        )

        self.turret.turretDisable()
        wpilib.simulation.restartTiming()
        wpilib.simulation.pauseTiming()

    # ---- Basic motor control tests ----

    def test_set_motor_voltage(self):
        """Test that setMotorVoltage applies voltage to the motor."""
        self.turret.setMotorVoltage(6.0)
        # motor.get() returns duty cycle: 6V / 12V bus = 0.5
        applied = self.motor.get()
        self.assertAlmostEqual(applied, 6.0 / 12.0, places=1)

    def test_set_motor_voltage_negative(self):
        """Test that negative voltage is applied correctly."""
        self.turret.setMotorVoltage(-6.0)
        applied = self.motor.get()
        self.assertAlmostEqual(applied, -6.0 / 12.0, places=1)

    def test_set_position_and_periodic(self):
        """Test that setPosition stores target and periodic drives PID."""
        self.turret.controller.setP(1.0)
        target_degrees = 45.0
        self.turret.setPosition(target_degrees)
        # periodic() drives the WPILib PID controller which sets motor voltage
        self.turret.periodic()
        applied = self.motor.get()
        self.assertNotEqual(applied, 0.0)
        self.turret.controller.setP(0.0)

    def test_get_position_with_simulated_encoder(self):
        """Test that getPosition returns the simulated encoder value."""
        simulated_position = 30.0  # degrees
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setPosition(simulated_position)
        position = self.turret.getPosition()
        self.assertAlmostEqual(position, simulated_position, places=1)

    def test_get_velocity_with_simulated_encoder(self):
        """Test that getVelocity returns the simulated encoder velocity."""
        simulated_velocity = 10.0  # degrees per second
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setVelocity(simulated_velocity)
        velocity = self.turret.getVelocity()
        self.assertAlmostEqual(velocity, simulated_velocity, places=1)

    def test_soft_limits_configured(self):
        """Test that soft limits are properly configured on the SparkMax."""
        config_accessor = self.motor.configAccessor
        self.assertTrue(
            config_accessor.softLimit.getForwardSoftLimitEnabled()
        )
        self.assertTrue(
            config_accessor.softLimit.getReverseSoftLimitEnabled()
        )
        self.assertAlmostEqual(
            config_accessor.softLimit.getForwardSoftLimit(),
            self.MAX_SOFT_LIMIT,
            places=1
        )
        self.assertAlmostEqual(
            config_accessor.softLimit.getReverseSoftLimit(),
            self.MIN_SOFT_LIMIT,
            places=1
        )

    def test_position_zero(self):
        """Test that setting position to zero stores the target."""
        self.turret.setPosition(0.0)
        self.assertEqual(self.turret._target_position, 0.0)

    def test_encoder_conversion_factor_configured(self):
        """Test that the encoder conversion factor is applied."""
        config_accessor = self.motor.configAccessor
        self.assertAlmostEqual(
            config_accessor.encoder.getPositionConversionFactor(),
            self.POSITION_CONVERSION_FACTOR,
            places=3
        )
        expected_velocity_cf = self.POSITION_CONVERSION_FACTOR / 60.0
        self.assertAlmostEqual(
            config_accessor.encoder.getVelocityConversionFactor(),
            expected_velocity_cf,
            places=5
        )

    def test_idle_mode_is_brake(self):
        """Test that the motor is configured in brake mode."""
        config_accessor = self.motor.configAccessor
        self.assertEqual(
            config_accessor.getIdleMode(),
            rev.SparkBaseConfig.IdleMode.kBrake
        )

    # ---- turretDisable and periodic idle tests ----

    def test_turret_disable_clears_target(self):
        """Test that turretDisable clears the target position."""
        self.turret.setPosition(45.0)
        self.turret.turretDisable()
        self.assertIsNone(self.turret._target_position)

    def test_periodic_idle_when_disabled(self):
        """Test that periodic does not drive motor when disabled."""
        self.turret.turretDisable()
        self.turret.periodic()
        # Motor should remain stopped (duty cycle 0)
        self.assertAlmostEqual(self.motor.get(), 0.0, places=1)

    # ---- Homing init tests (via calibration controller) ----

    def test_homing_init_saves_and_applies_settings(self):
        """Test that homing_init changes current limit and disables
        the soft limit in the homing direction."""
        original_current = self.motor.configAccessor.getSmartCurrentLimit()
        self.turret.calibration.homing_init(
            max_current=10.0,
            max_power_pct=0.2,
            max_homing_time=5.0,
            homing_forward=True
        )
        self.assertTrue(self.turret.is_homing)
        # Current limit should be changed to homing value
        self.assertAlmostEqual(
            self.motor.configAccessor.getSmartCurrentLimit(), 10.0, places=0
        )
        # Forward soft limit should be disabled for forward homing
        self.assertFalse(
            self.motor.configAccessor.softLimit.getForwardSoftLimitEnabled()
        )
        # Reverse soft limit should still be enabled
        self.assertTrue(
            self.motor.configAccessor.softLimit.getReverseSoftLimitEnabled()
        )
        # Cleanup: verify original current was saved (now in _saved_config dict)
        self.assertAlmostEqual(
            self.turret.calibration._saved_config['current_limit'],
            original_current, places=0
        )

    def test_homing_blocks_set_position(self):
        """Test that setPosition is blocked during homing."""
        self.turret.calibration.homing_init(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, homing_forward=True
        )
        self.turret.setPosition(45.0)
        self.assertIsNone(self.turret._target_position)

    def test_homing_blocks_set_motor_voltage(self):
        """Test that setMotorVoltage is blocked during homing."""
        self.turret.calibration.homing_init(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, homing_forward=True
        )
        # Stop motor first to have a known state
        self.motor.stopMotor()
        self.turret.setMotorVoltage(6.0)
        # Should still be 0 since setMotorVoltage was blocked
        self.assertAlmostEqual(self.motor.get(), 0.0, places=1)

    # ---- Homing periodic tests (via calibration controller) ----

    def test_homing_periodic_drives_motor_forward(self):
        """Test that homing drives motor in forward direction."""
        self.turret.calibration.homing_init(
            max_current=10.0, max_power_pct=0.3,
            max_homing_time=5.0, homing_forward=True
        )
        # Set velocity above threshold so stall isn't triggered
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setVelocity(50.0)
        result = self.turret.calibration._homing_periodic()
        self.assertFalse(result)
        self.assertAlmostEqual(self.motor.get(), 0.3, places=1)

    def test_homing_periodic_drives_motor_reverse(self):
        """Test that homing drives motor in reverse direction."""
        self.turret.calibration.homing_init(
            max_current=10.0, max_power_pct=0.3,
            max_homing_time=5.0, homing_forward=False
        )
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setVelocity(-50.0)
        result = self.turret.calibration._homing_periodic()
        self.assertFalse(result)
        self.assertAlmostEqual(self.motor.get(), -0.3, places=1)

    def test_homing_periodic_detects_stall(self):
        """Test that homing detects stall after 100ms of low
        velocity and completes."""
        self.turret.calibration.homing_init(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, homing_forward=False,
            min_velocity=1.0
        )
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setVelocity(0.0)

        # First call starts the stall timer
        result = self.turret.calibration._homing_periodic()
        self.assertFalse(result)

        # Advance time past 100ms stall threshold
        wpilib.simulation.stepTiming(0.15)

        # Next call should detect stall and complete
        result = self.turret.calibration._homing_periodic()
        self.assertTrue(result)
        self.assertFalse(self.turret.is_homing)

    def test_homing_resets_encoder_forward(self):
        """Test that encoder is reset to max_soft_limit when homing
        forward completes."""
        self.turret.calibration.homing_init(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, homing_forward=True,
            min_velocity=1.0
        )
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setVelocity(0.0)

        # Trigger stall detection
        self.turret.calibration._homing_periodic()
        wpilib.simulation.stepTiming(0.15)
        self.turret.calibration._homing_periodic()

        position = self.turret.getPosition()
        self.assertAlmostEqual(position, self.MAX_SOFT_LIMIT, places=1)

    def test_homing_resets_encoder_reverse(self):
        """Test that encoder is reset to min_soft_limit when homing
        reverse completes."""
        self.turret.calibration.homing_init(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, homing_forward=False,
            min_velocity=1.0
        )
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setVelocity(0.0)

        # Trigger stall detection
        self.turret.calibration._homing_periodic()
        wpilib.simulation.stepTiming(0.15)
        self.turret.calibration._homing_periodic()

        position = self.turret.getPosition()
        self.assertAlmostEqual(position, self.MIN_SOFT_LIMIT, places=1)

    def test_homing_end_restores_settings(self):
        """Test that homing end restores current limit and soft limits."""
        original_current = self.motor.configAccessor.getSmartCurrentLimit()
        self.turret.calibration.homing_init(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, homing_forward=True
        )
        # Verify settings changed
        self.assertAlmostEqual(
            self.motor.configAccessor.getSmartCurrentLimit(), 10.0, places=0
        )

        self.turret.calibration._homing_end(abort=False)

        # Settings should be restored
        self.assertAlmostEqual(
            self.motor.configAccessor.getSmartCurrentLimit(),
            original_current, places=0
        )
        self.assertTrue(
            self.motor.configAccessor.softLimit.getForwardSoftLimitEnabled()
        )
        self.assertTrue(
            self.motor.configAccessor.softLimit.getReverseSoftLimitEnabled()
        )
        self.assertFalse(self.turret.is_homing)

    def test_homing_end_abort(self):
        """Test that homing abort stops motor and restores state."""
        self.turret.calibration.homing_init(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, homing_forward=True
        )
        self.turret.calibration._homing_end(abort=True)

        self.assertFalse(self.turret.is_homing)
        self.assertAlmostEqual(self.motor.get(), 0.0, places=1)
        self.assertTrue(
            self.motor.configAccessor.softLimit.getForwardSoftLimitEnabled()
        )

    def test_homing_timeout(self):
        """Test that homing times out and reports failure."""
        self.turret.calibration.homing_init(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=0.5,
            homing_forward=True,
            min_velocity=1.0
        )
        # Set velocity above threshold so stall doesn't trigger
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setVelocity(50.0)

        # Advance past timeout
        wpilib.simulation.stepTiming(0.6)

        result = self.turret.calibration._homing_periodic()
        self.assertTrue(result)
        self.assertFalse(self.turret.is_homing)
        # Settings should be restored
        self.assertTrue(
            self.motor.configAccessor.softLimit.getForwardSoftLimitEnabled()
        )

    # ---- Periodic integration tests ----

    def test_periodic_drives_to_target(self):
        """Test that periodic drives PID to stored target position."""
        self.turret.controller.setP(1.0)
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setPosition(0.0)
        target = 30.0
        self.turret.setPosition(target)
        self.turret.periodic()
        applied = self.motor.get()
        self.assertNotEqual(applied, 0.0)
        self.turret.controller.setP(0.0)

    def test_periodic_calls_homing_when_active(self):
        """Test that periodic calls calibration.periodic when homing."""
        self.turret.calibration.homing_init(
            max_current=10.0, max_power_pct=0.25,
            max_homing_time=5.0, homing_forward=True
        )
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setVelocity(50.0)

        self.turret.periodic()
        # Motor should be driven by homing, not PID
        self.assertAlmostEqual(self.motor.get(), 0.25, places=2)

    def test_voltage_clamping(self):
        """Test that PID output is clamped to voltage limits."""
        self.turret.controller.setP(10.0)
        self.turret._max_output_voltage = 2.0
        self.turret._min_output_voltage = -2.0
        self.turret.setPosition(45.0)
        self.turret.periodic()
        applied = self.motor.get()
        # Duty cycle should be at most 2.0/12.0
        self.assertLessEqual(abs(applied), 2.0 / 12.0 + 0.01)
        self.assertNotEqual(applied, 0.0)
        # Cleanup
        self.turret.controller.setP(0.0)
        self.turret._max_output_voltage = 12.0
        self.turret._min_output_voltage = -12.0

    def test_pid_controller_published_as_sendable(self):
        """Test that PIDController is published to SmartDashboard as Sendable."""
        prefix = self.turret.getName() + "/pid"
        sd = wpilib.SmartDashboard
        # putData was called in __init__, verify the entry exists
        self.assertTrue(sd.containsKey(prefix + "/p"))
        self.assertTrue(sd.containsKey(prefix + "/i"))
        self.assertTrue(sd.containsKey(prefix + "/d"))

    def test_mechanism2d_exists(self):
        """Test that Mechanism2d and arms are created on the turret."""
        self.assertIsNotNone(self.turret.mech2d)
        self.assertIsNotNone(self.turret.mech_current_arm)
        self.assertIsNotNone(self.turret.mech_target_arm)

    def test_mechanism2d_telemetry_no_error(self):
        """Test that updateTelemetry updates Mechanism2d arms without error."""
        self.turret.setPosition(60.0)
        # Should not raise any exceptions
        self.turret.updateTelemetry()

    def test_set_position_clamps_above_max(self):
        """Test that setPosition clamps values above max soft limit."""
        self.turret.setPosition(200.0)
        self.assertEqual(self.turret._target_position, self.MAX_SOFT_LIMIT)

    def test_set_position_clamps_below_min(self):
        """Test that setPosition clamps values below min soft limit."""
        self.turret.setPosition(-200.0)
        self.assertEqual(self.turret._target_position, self.MIN_SOFT_LIMIT)

    def test_set_position_within_limits(self):
        """Test that setPosition accepts values within soft limits."""
        self.turret.setPosition(45.0)
        self.assertEqual(self.turret._target_position, 45.0)

    # ---- Calibration tests (via calibration controller) ----

    def test_calibration_init_sets_state(self):
        """Test that calibration_init sets calibration flags and phase."""
        self.turret.calibration.calibration_init(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, min_velocity=1.0
        )
        self.assertTrue(self.turret.calibration.is_calibrating)
        self.assertEqual(self.turret.calibration._calibration_phase, 1)
        self.assertTrue(self.turret.calibration.is_homing)
        # Both soft limits should be disabled
        ca = self.motor.configAccessor
        self.assertFalse(ca.softLimit.getForwardSoftLimitEnabled())
        self.assertFalse(ca.softLimit.getReverseSoftLimitEnabled())

    def test_calibration_blocks_set_position(self):
        """Test that setPosition is blocked during calibration."""
        self.turret.calibration.calibration_init(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, min_velocity=1.0
        )
        self.turret.setPosition(45.0)
        self.assertIsNone(self.turret._target_position)

    def test_calibration_blocks_set_motor_voltage(self):
        """Test that setMotorVoltage is blocked during calibration."""
        self.turret.calibration.calibration_init(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, min_velocity=1.0
        )
        self.motor.stopMotor()
        self.turret.setMotorVoltage(6.0)
        self.assertAlmostEqual(self.motor.get(), 0.0, places=1)

    def test_calibration_phase1_sets_zero(self):
        """Test that phase 1 completion sets encoder to 0."""
        self.turret.calibration.calibration_init(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, min_velocity=1.0
        )
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setVelocity(0.0)
        # Trigger stall detection
        self.turret.calibration._calibration_periodic()
        wpilib.simulation.stepTiming(0.15)
        self.turret.calibration._calibration_periodic()
        # Phase 1 complete - encoder should be 0, phase should be 2
        self.assertEqual(self.turret.calibration.min_limit, 0.0)
        self.assertEqual(self.turret.calibration._calibration_phase, 2)
        self.assertTrue(self.turret.calibration.is_calibrating)

    def test_calibration_full_sequence(self):
        """Test complete two-phase calibration sets hard limits and
        computes soft limits."""
        self.turret.calibration.calibration_init(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, min_velocity=1.0
        )
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setVelocity(0.0)
        # Phase 1: stall reverse
        self.turret.calibration._calibration_periodic()
        wpilib.simulation.stepTiming(0.15)
        self.turret.calibration._calibration_periodic()
        # Now in phase 2, set a simulated position for the forward limit
        encoder_sim.setPosition(180.0)
        encoder_sim.setVelocity(0.0)
        # Phase 2: stall forward
        self.turret.calibration._calibration_periodic()
        wpilib.simulation.stepTiming(0.15)
        self.turret.calibration._calibration_periodic()
        # Calibration complete
        self.assertFalse(self.turret.calibration.is_calibrating)
        self.assertTrue(self.turret.calibration.is_calibrated)
        self.assertEqual(self.turret.calibration.min_limit, 0.0)
        self.assertEqual(self.turret.calibration.max_limit, 180.0)
        # Soft limits with 5% margin: 9.0 and 171.0
        self.assertAlmostEqual(
            self.turret.calibration.min_soft_limit, 9.0, places=1)
        self.assertAlmostEqual(
            self.turret.calibration.max_soft_limit, 171.0, places=1)
        # Soft limits applied to motor
        ca = self.motor.configAccessor
        self.assertTrue(ca.softLimit.getForwardSoftLimitEnabled())
        self.assertTrue(ca.softLimit.getReverseSoftLimitEnabled())
        self.assertAlmostEqual(
            ca.softLimit.getForwardSoftLimit(), 171.0, places=1)
        self.assertAlmostEqual(
            ca.softLimit.getReverseSoftLimit(), 9.0, places=1)

    def test_set_soft_limit_margin(self):
        """Test that set_soft_limit_margin recalculates and applies limits."""
        # Manually set calibrated state
        self.turret.calibration._is_calibrated = True
        self.turret.calibration._hard_limit_min = 0.0
        self.turret.calibration._hard_limit_max = 200.0
        self.turret.calibration.set_soft_limit_margin(0.10)
        self.assertAlmostEqual(
            self.turret.calibration.min_soft_limit, 20.0, places=1)
        self.assertAlmostEqual(
            self.turret.calibration.max_soft_limit, 180.0, places=1)
        self.assertAlmostEqual(
            self.turret.calibration.soft_limit_margin, 0.10)

    def test_set_soft_limit_margin_requires_calibrated(self):
        """Test that set_soft_limit_margin does nothing if not calibrated."""
        original_min = self.turret.calibration.min_soft_limit
        original_max = self.turret.calibration.max_soft_limit
        self.turret.calibration.set_soft_limit_margin(0.10)
        self.assertEqual(
            self.turret.calibration.min_soft_limit, original_min)
        self.assertEqual(
            self.turret.calibration.max_soft_limit, original_max)

    def test_calibration_telemetry(self):
        """Test that calibration telemetry keys are published."""
        self.turret.updateTelemetry()
        prefix = self.turret.getName() + "/"
        sd = wpilib.SmartDashboard
        self.assertTrue(sd.containsKey(prefix + "isCalibrated"))
        self.assertTrue(sd.containsKey(prefix + "isCalibrating"))
        self.assertTrue(sd.containsKey(prefix + "hardLimitMin"))
        self.assertTrue(sd.containsKey(prefix + "hardLimitMax"))
        self.assertTrue(sd.containsKey(prefix + "positionOffset"))
        self.assertTrue(sd.containsKey(prefix + "softLimitMargin"))

    def test_calibration_single_direction_known_range(self):
        """Test single-direction calibration with known range skips phase 2."""
        self.turret.calibration.calibration_init(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, min_velocity=1.0,
            known_range=180.0
        )
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setVelocity(0.0)
        # Phase 1: stall reverse
        self.turret.calibration._calibration_periodic()
        wpilib.simulation.stepTiming(0.15)
        self.turret.calibration._calibration_periodic()
        # Should complete after phase 1 only
        self.assertFalse(self.turret.calibration.is_calibrating)
        self.assertTrue(self.turret.calibration.is_calibrated)
        self.assertEqual(self.turret.calibration.min_limit, 0.0)
        self.assertEqual(self.turret.calibration.max_limit, 180.0)
        # Soft limits with 5% margin
        self.assertAlmostEqual(
            self.turret.calibration.min_soft_limit, 9.0, places=1)
        self.assertAlmostEqual(
            self.turret.calibration.max_soft_limit, 171.0, places=1)

    def test_calibration_abort_restores_settings(self):
        """Test that calibration abort restores original soft limits."""
        self.turret.calibration.calibration_init(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, min_velocity=1.0
        )
        self.turret.calibration._calibration_end(abort=True)
        self.assertFalse(self.turret.calibration.is_calibrating)
        self.assertFalse(self.turret.calibration.is_calibrated)
        # Soft limits should be restored
        ca = self.motor.configAccessor
        self.assertTrue(ca.softLimit.getForwardSoftLimitEnabled())
        self.assertTrue(ca.softLimit.getReverseSoftLimitEnabled())


if __name__ == "__main__":
    unittest.main()
