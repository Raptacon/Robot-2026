#
# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.
#

import wpilib
import rev
import commands2
import wpimath.controller
import wpimath.trajectory

class TurretConstants:
    kP = 0
    kI = 0

    kMaxVelocityRadPerSecond = 3
    kMotorCAN = 53
    kMotorToTurretConversionFactor = 1/11
    kMaxAccelerationRadPerSecSquared = 10


class TurretSubsystem(commands2.ProfiledPIDSubsystem):
    """A turret subsystem that moves with a motion profile."""

    def __init__(self) -> None:
        super().__init__(
            wpimath.controller.ProfiledPIDController(
                TurretConstants.kP,
                TurretConstants.kI,
                0,
                wpimath.trajectory.TrapezoidProfile.Constraints(
                    TurretConstants.kMaxVelocityRadPerSecond,
                    TurretConstants.kMaxAccelerationRadPerSecSquared,
                ),
            ),
            0,
        )

        config = rev.SparkMaxConfig()
        config.encoder.positionConversionFactor(TurretConstants.kMotorToTurretConversionFactor)
        self.motor = rev.SparkMax(TurretConstants.kMotorCAN,rev.SparkLowLevel.MotorType.kBrushless)
        self.motor.configure(config, rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kNoPersistParameters)
        self.encoder = self.motor.getEncoder()

        self.setGoal(0)

    def getMeasurement(self) -> float:
        """
        Return position of the turret in rotations
        
        :param self: A turret subsystem
        :return: Position of the turret in rotations
        :rtype: float
        """
        return self.encoder.getPosition()