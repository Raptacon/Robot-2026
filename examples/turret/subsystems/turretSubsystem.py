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
from ntcore import NetworkTableInstance

class TurretConstants:
    kP = 5
    kI = 5

    kMaxVelocityRPM = 10
    kMotorCAN = 40
    kMotorToTurretConversionFactor = 1/6.6
    kMaxAccelerationRPMPM = 20000
    kMaxVoltage = 1.5


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
        self.networkTable = NetworkTableInstance.getDefault()
        wpilib.SmartDashboard.putData("pid", self._controller)

        config = rev.SparkMaxConfig()
        config.encoder.positionConversionFactor(TurretConstants.kMotorToTurretConversionFactor)
        config.encoder.velocityConversionFactor(TurretConstants.kMotorToTurretConversionFactor)
        self.motor = rev.SparkMax(TurretConstants.kMotorCAN,rev.SparkLowLevel.MotorType.kBrushless)
        self.motor.configure(config, rev.ResetMode.kNoResetSafeParameters, rev.PersistMode.kNoPersistParameters)
        self.encoder = self.motor.getEncoder()
        self.encoder.setPosition(0)

        self.setGoal(0)
    
    def useOutput(self, output, setpoint):
        if abs(output) > TurretConstants.kMaxVoltage:
            if output > -1*TurretConstants.kMaxVoltage:
                output = TurretConstants.kMaxVoltage
            elif output < -1*TurretConstants.kMaxVoltage:
                output = -1*TurretConstants.kMaxVoltage
        self.motor.setVoltage(output)

    def getMeasurement(self) -> float:
        """
        Return position of the turret in rotations
        
        :param self: A turret subsystem
        :return: Position of the turret in rotations
        :rtype: float
        """
        return self.encoder.getPosition()