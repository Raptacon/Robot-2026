"""
Physical constants for the intake mechanism.
"""

from enum import Enum


class CaptainPlanetConsts:
    kIntakeMotorCanId = 40
    kRollerMotorCanId = 41
    kMotorInverted = False
    kCurrentLimitAmps = 30
    # kBreakBeam = 2
    # kFrontBreakBeam = 2
    # kBackBreakBeam = 0
    # kHallEffectSensor = 6
    kDefaultSpeed = 0.15
    kOperatorDampener = 0.15

    class BreakBeamActionOptions(Enum):
        DONOTHING = 1
        TOFRONT = 2
        TOBACK = 3
