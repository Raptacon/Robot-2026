"""
Unit tests for the Turret subsystem.

Tests validate:
- Motor output behavior for voltage and position control commands
- Simulated encoder position and velocity feedback
- Soft limit configuration
- Encoder conversion factor configuration
- Homing routine: init, periodic stall detection, timeout, cleanup
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
        # End any active homing to restore settings
        if self.turret.is_homing:
            self.turret.homingEnd(abort=True)
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
        target_degrees = 45.0
        self.turret.setPosition(target_degrees)
        # periodic() drives the PID controller
        self.turret.periodic()
        setpoint = self.motor_sim.getSetpoint()
        self.assertAlmostEqual(setpoint, target_degrees, places=1)

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
        """Test that setting position to zero works via periodic."""
        self.turret.setPosition(0.0)
        self.turret.periodic()
        setpoint = self.motor_sim.getSetpoint()
        self.assertAlmostEqual(setpoint, 0.0, places=1)

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

    # ---- Homing init tests ----

    def test_homing_init_saves_and_applies_settings(self):
        """Test that homingInit changes current limit and disables
        the soft limit in the homing direction."""
        original_current = self.motor.configAccessor.getSmartCurrentLimit()
        self.turret.homingInit(
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
        # Cleanup: verify original current was saved
        self.assertAlmostEqual(
            self.turret._saved_current_limit, original_current, places=0
        )

    def test_homing_blocks_set_position(self):
        """Test that setPosition is blocked during homing."""
        self.turret.homingInit(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, homing_forward=True
        )
        self.turret.setPosition(45.0)
        self.assertIsNone(self.turret._target_position)

    def test_homing_blocks_set_motor_voltage(self):
        """Test that setMotorVoltage is blocked during homing."""
        self.turret.homingInit(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, homing_forward=True
        )
        # Stop motor first to have a known state
        self.motor.stopMotor()
        self.turret.setMotorVoltage(6.0)
        # Should still be 0 since setMotorVoltage was blocked
        self.assertAlmostEqual(self.motor.get(), 0.0, places=1)

    # ---- Homing periodic tests ----

    def test_homing_periodic_drives_motor_forward(self):
        """Test that homingPeriodic drives motor in forward direction."""
        self.turret.homingInit(
            max_current=10.0, max_power_pct=0.3,
            max_homing_time=5.0, homing_forward=True
        )
        # Set velocity above threshold so stall isn't triggered
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setVelocity(50.0)
        result = self.turret.homingPeriodic()
        self.assertFalse(result)
        self.assertAlmostEqual(self.motor.get(), 0.3, places=1)

    def test_homing_periodic_drives_motor_reverse(self):
        """Test that homingPeriodic drives motor in reverse direction."""
        self.turret.homingInit(
            max_current=10.0, max_power_pct=0.3,
            max_homing_time=5.0, homing_forward=False
        )
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setVelocity(-50.0)
        result = self.turret.homingPeriodic()
        self.assertFalse(result)
        self.assertAlmostEqual(self.motor.get(), -0.3, places=1)

    def test_homing_periodic_detects_stall(self):
        """Test that homingPeriodic detects stall after 100ms of low
        velocity and completes homing."""
        self.turret.homingInit(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, homing_forward=False,
            min_velocity=1.0
        )
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setVelocity(0.0)

        # First call starts the stall timer
        result = self.turret.homingPeriodic()
        self.assertFalse(result)

        # Advance time past 100ms stall threshold
        wpilib.simulation.stepTiming(0.15)

        # Next call should detect stall and complete
        result = self.turret.homingPeriodic()
        self.assertTrue(result)
        self.assertFalse(self.turret.is_homing)

    def test_homing_resets_encoder_forward(self):
        """Test that encoder is reset to max_soft_limit when homing
        forward completes."""
        self.turret.homingInit(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, homing_forward=True,
            min_velocity=1.0
        )
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setVelocity(0.0)

        # Trigger stall detection
        self.turret.homingPeriodic()
        wpilib.simulation.stepTiming(0.15)
        self.turret.homingPeriodic()

        position = self.turret.getPosition()
        self.assertAlmostEqual(position, self.MAX_SOFT_LIMIT, places=1)

    def test_homing_resets_encoder_reverse(self):
        """Test that encoder is reset to min_soft_limit when homing
        reverse completes."""
        self.turret.homingInit(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, homing_forward=False,
            min_velocity=1.0
        )
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setVelocity(0.0)

        # Trigger stall detection
        self.turret.homingPeriodic()
        wpilib.simulation.stepTiming(0.15)
        self.turret.homingPeriodic()

        position = self.turret.getPosition()
        self.assertAlmostEqual(position, self.MIN_SOFT_LIMIT, places=1)

    def test_homing_end_restores_settings(self):
        """Test that homingEnd restores current limit and soft limits."""
        original_current = self.motor.configAccessor.getSmartCurrentLimit()
        self.turret.homingInit(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, homing_forward=True
        )
        # Verify settings changed
        self.assertAlmostEqual(
            self.motor.configAccessor.getSmartCurrentLimit(), 10.0, places=0
        )

        self.turret.homingEnd(abort=False)

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
        """Test that homingEnd with abort stops motor and restores state."""
        self.turret.homingInit(
            max_current=10.0, max_power_pct=0.2,
            max_homing_time=5.0, homing_forward=True
        )
        self.turret.homingEnd(abort=True)

        self.assertFalse(self.turret.is_homing)
        self.assertAlmostEqual(self.motor.get(), 0.0, places=1)
        self.assertTrue(
            self.motor.configAccessor.softLimit.getForwardSoftLimitEnabled()
        )

    def test_homing_timeout(self):
        """Test that homing times out and reports failure."""
        self.turret.homingInit(
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

        result = self.turret.homingPeriodic()
        self.assertTrue(result)
        self.assertFalse(self.turret.is_homing)
        # Settings should be restored
        self.assertTrue(
            self.motor.configAccessor.softLimit.getForwardSoftLimitEnabled()
        )

    # ---- Periodic integration tests ----

    def test_periodic_drives_to_target(self):
        """Test that periodic drives PID to stored target position."""
        target = 30.0
        self.turret.setPosition(target)
        self.turret.periodic()
        setpoint = self.motor_sim.getSetpoint()
        self.assertAlmostEqual(setpoint, target, places=1)

    def test_periodic_calls_homing_when_active(self):
        """Test that periodic calls homingPeriodic when homing is active."""
        self.turret.homingInit(
            max_current=10.0, max_power_pct=0.25,
            max_homing_time=5.0, homing_forward=True
        )
        encoder_sim = self.motor_sim.getRelativeEncoderSim()
        encoder_sim.setVelocity(50.0)

        self.turret.periodic()
        # Motor should be driven by homing, not PID
        self.assertAlmostEqual(self.motor.get(), 0.25, places=2)


if __name__ == "__main__":
    unittest.main()
