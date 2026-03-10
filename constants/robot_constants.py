"""
Physical constants for the overall robot.
"""


class RobotConstants:
    massKG: float = 63.9565
    # MOI: Moment of inertia, kg*m^2
    MOI: float = 5.94175290870316
    # Robot loop frequency and period
    kPeriodicFreqHz: float = 50.0
    kPeriodicPeriodSec: float = 1.0 / kPeriodicFreqHz
