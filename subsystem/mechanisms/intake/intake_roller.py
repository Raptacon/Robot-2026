"""IntakeRoller subsystem — single motor for intake rollers."""

from constants.swerve_constants import IntakeRollerConstants
from subsystem.mechanisms.simple_motor_subsystem import SimpleMotorSubsystem


class IntakeRoller(SimpleMotorSubsystem):
    def __init__(self):
        super().__init__(IntakeRollerConstants)
