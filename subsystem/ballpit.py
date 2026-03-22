import commands2
import rev
import wpilib
from constants.swerve_constants import BallpitConstants

class BallPitHopper(commands2.Subsystem):
    def __init__(self) -> None:
        """
        Creates the hopper motor
        
        Returns:
            None - class initialization executed upon construction
        """
        self.hopperMotor = rev.SparkMax(BallpitConstants.hopperCanId, rev.SparkLowLevel.MotorType.kBrushless)
        self.hopperConfig = rev.SparkBaseConfig()
        self.hopperConfig.closedLoop.pidf(0, 0, 0, 1/473, rev.ClosedLoopSlot.kSlot0)
        self.hopperMotorPIDF = self.hopperMotor.getClosedLoopController()
        self.hopperMotor.configure(self.hopperConfig, rev.ResetMode.kResetSafeParameters, rev.PersistMode.kPersistParameters)
        self.lastSpeed = 0
        self.toggleHopper = False

    def setHexShaftSpeed(self, velocity : float):
        """
        Sets the motor velocity for use elsewhere

        Args:
            velocity: speed of the hopper motor from -2000 to 2000

        Returns:
            None - function to be used elsewhere
        """
        self.lastSpeed = velocity

    def zeroHopperVelocity(self):
        self.setHexShaftSpeed(0)

    def getLastSpeed(self):
        return self.lastSpeed

    def unjamHopper(self, velocity, repeat, duration):
        pre_unjamSpeed = self.getLastSpeed()
        self.toggleHopper = False
        return commands2.cmd.sequence(
            commands2.cmd.repeatingSequence(
                self.hex_shaft_generator(-velocity).withTimeout(duration),
                self.hex_shaft_generator(velocity).withTimeout(duration),
            ).withTimeout(repeat * (duration * 2)),
            self.hex_shaft_generator(pre_unjamSpeed)
        )

    def hex_shaft_generator(self, velocity):
        return commands2.cmd.run(lambda: self.setHexShaftSpeed(velocity), self)
        # self.setHexShaftSpeed(velocity)

    def overrideHopperMotor(self):
        self.toggleHopper = not self.toggleHopper

    def periodic(self):
        if self.toggleHopper:
            self.lastSpeed = BallpitConstants.motorGo
            self.hopperMotorPIDF.setReference(self.lastSpeed, rev.SparkLowLevel.ControlType.kVelocity, rev.ClosedLoopSlot.kSlot0)
        else:
            self.lastSpeed = 0
            self.hopperMotorPIDF.setReference(self.lastSpeed, rev.SparkLowLevel.ControlType.kVelocity, rev.ClosedLoopSlot.kSlot0)
        wpilib.SmartDashboard.putNumber("lastspeed hopper", self.lastSpeed)
