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
    kP = 3
    kI = 0.0015

    kMaxVelocityRPM = 1000
    kMotorCAN = 40
    kMotorToTurretConversionFactor = 1/11
    kMaxAccelerationRPMPM = 60000


class TurretSubsystem(commands2.ProfiledPIDSubsystem):
    """A turret subsystem that moves with a motion profile."""

    def __init__(self) -> None:
        super().__init__(
            wpimath.controller.ProfiledPIDController(
                TurretConstants.kP,
                TurretConstants.kI,
                0,
                wpimath.trajectory.TrapezoidProfile.Constraints(
                    TurretConstants.kMaxVelocityRPM,
                    TurretConstants.kMaxAccelerationRPMPM,
                ),
            ),
            0,
        )

        config = rev.SparkMaxConfig()
        config.encoder.positionConversionFactor(TurretConstants.kMotorToTurretConversionFactor)
        config.encoder.velocityConversionFactor(TurretConstants.kMotorToTurretConversionFactor)
        self.motor = rev.SparkMax(TurretConstants.kMotorCAN,rev.SparkLowLevel.MotorType.kBrushless)
        self.motor.configure(config, rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kNoPersistParameters)
        self.encoder = self.motor.getEncoder()
        self.encoder.setPosition(0)

        self.setGoal(0)
    
    def useOutput(self, output, setpoint):
        self.motor.setVoltage(output)

    def getMeasurement(self) -> float:
        """
        Return position of the turret in rotations
        
        :param self: A turret subsystem
        :return: Position of the turret in rotations
        :rtype: float
        """
        return self.encoder.getPosition()