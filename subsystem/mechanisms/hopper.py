"""Hopper subsystem — single motor, duty-cycle control."""

from constants.swerve_constants import HopperConstants
from subsystem.mechanisms.simple_motor_subsystem import SimpleMotorSubsystem


class Hopper(SimpleMotorSubsystem):
    def __init__(self):
        super().__init__(HopperConstants)
