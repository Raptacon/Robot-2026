"""Base class for single-motor, duty-cycle-only subsystems.

Provides motor setup, setPower/stop/getPower, NT telemetry under
/subsystems/<name>/, and a Mechanism2d visualization whose ligament
length represents motor power magnitude.
"""

from commands2 import Subsystem
import ntcore
import rev
import wpilib


class SimpleMotorSubsystem(Subsystem):
    """A single SparkMax/SparkFlex motor controlled by duty cycle.

    The constants object must provide:
        name: str           -- subsystem name and NT path component
        canId: int          -- CAN ID for the motor controller
        inverted: bool      -- whether to invert motor direction
        motorClass          -- (optional) rev.SparkMax or rev.SparkFlex,
                               defaults to rev.SparkMax
    """

    _MECH_WIDTH = 100
    _MECH_HEIGHT = 50
    _MECH_MAX_LENGTH = 80

    def __init__(self, constants):
        super().__init__()
        self._power = 0.0
        self._name = constants.name

        # Motor setup
        motor_class = getattr(constants, 'motorClass', rev.SparkMax)
        self.motor = motor_class(
            constants.canId,
            rev.SparkLowLevel.MotorType.kBrushless,
        )
        config = rev.SparkBaseConfig()
        config.inverted(constants.inverted)
        current_limit = getattr(constants, 'currentLimitAmps', 30)
        config.smartCurrentLimit(current_limit)
        self.motor.configure(
            config,
            rev.ResetMode.kResetSafeParameters,
            rev.PersistMode.kPersistParameters,
        )
        self.encoder = self.motor.getEncoder()

        # NT telemetry under /subsystems/<name>/
        table = ntcore.NetworkTableInstance.getDefault().getTable(
            f"subsystems/{self._name}"
        )
        self._nt_power = table.getDoubleTopic("power").publish()
        self._nt_velocity = table.getDoubleTopic("velocity").publish()

        # Mechanism2d visualization
        self._mech = wpilib.Mechanism2d(self._MECH_WIDTH, self._MECH_HEIGHT)
        root = self._mech.getRoot(
            "root", self._MECH_WIDTH / 2, self._MECH_HEIGHT / 2
        )
        self._mech_ligament = root.appendLigament(
            "power", 0, 0, 6,
            wpilib.Color8Bit(128, 128, 128)
        )
        wpilib.SmartDashboard.putData(f"{self._name}/mechanism", self._mech)

        self.setName(self._name)

    def setPower(self, power: float):
        """Set motor duty cycle (-1.0 to 1.0)."""
        self._power = power

    def stop(self):
        """Set motor power to zero."""
        self._power = 0.0

    def getPower(self) -> float:
        """Return last commanded power."""
        return self._power

    def periodic(self):
        self.motor.set(self._power)
        self._nt_power.set(self._power)
        self._nt_velocity.set(self.encoder.getVelocity())

        # Update Mechanism2d: length = magnitude, color = direction
        length = abs(self._power) * self._MECH_MAX_LENGTH
        if self._power > 0:
            color = wpilib.Color8Bit(wpilib.Color.kGreen)
        elif self._power < 0:
            color = wpilib.Color8Bit(wpilib.Color.kRed)
        else:
            color = wpilib.Color8Bit(128, 128, 128)
        self._mech_ligament.setLength(length)
        self._mech_ligament.setColor(color)
