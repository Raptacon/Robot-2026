import wpilib
from wpimath.geometry import Pose2d
from constants.field_target_constants_2026 import FieldTargets2026
from typing import Callable


def determineShooterTargets2026(odometry: Callable[[],Pose2d], alliance: wpilib.DriverStation.Alliance):
    """
    Using the odometer and the robot's alliance, determine where on the field the shooter
    should target.

    Args:
        odometry: polled current location and orientation of the robot on the field
        alliance: red or blue

    Returns:
        target: the field location the shooter should target
    """
    odometryTranslation = odometry().translation()
    if alliance == wpilib.DriverStation.Alliance.kRed:
        if odometryTranslation.X() > FieldTargets2026.redHubTarget[0]:
            target = FieldTargets2026.redHubTarget
        elif odometryTranslation.Y() < FieldTargets2026.redHubTarget[1]:
            target = FieldTargets2026.bottomRightTarget
        else:
            target = FieldTargets2026.topRightTarget
    else:
        if odometryTranslation.X() < FieldTargets2026.blueHubTarget[0]:
            target = FieldTargets2026.blueHubTarget
        elif odometryTranslation.Y() < FieldTargets2026.blueHubTarget[1]:
            target = FieldTargets2026.bottomLeftTarget
        else:
            target = FieldTargets2026.topLeftTarget
    return target
