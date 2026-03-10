#
# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.
#
# Based on the WPILib SwerveBot example:
# https://github.com/robotpy/examples/tree/main/SwerveBot
#

import math

import wpilib
import wpimath.controller
import wpimath.geometry
import wpimath.kinematics
import wpimath.trajectory

kWheelRadius = 0.0508
kEncoderResolution = 4096
kModuleMaxAngularVelocity = math.pi
kModuleMaxAngularAcceleration = math.tau


class SwerveModule:
    def __init__(
        self,
        driveMotorChannel: int,
        turningMotorChannel: int,
        driveEncoderChannelA: int,
        driveEncoderChannelB: int,
        turningEncoderChannelA: int,
        turningEncoderChannelB: int,
    ) -> None:
        """Constructs a SwerveModule with a drive motor, turning motor,
        drive encoder and turning encoder.

        :param driveMotorChannel:      PWM output for the drive motor.
        :param turningMotorChannel:    PWM output for the turning motor.
        :param driveEncoderChannelA:   DIO input for the drive encoder A
        :param driveEncoderChannelB:   DIO input for the drive encoder B
        :param turningEncoderChannelA: DIO input for the turning encoder A
        :param turningEncoderChannelB: DIO input for the turning encoder B
        """
        self.driveMotor = wpilib.PWMSparkMax(driveMotorChannel)
        self.turningMotor = wpilib.PWMSparkMax(turningMotorChannel)

        self.driveEncoder = wpilib.Encoder(
            driveEncoderChannelA, driveEncoderChannelB)
        self.turningEncoder = wpilib.Encoder(
            turningEncoderChannelA, turningEncoderChannelB)

        self.drivePIDController = wpimath.controller.PIDController(
            1, 0, 0)

        self.turningPIDController = (
            wpimath.controller.ProfiledPIDController(
                1, 0, 0,
                wpimath.trajectory.TrapezoidProfile.Constraints(
                    kModuleMaxAngularVelocity,
                    kModuleMaxAngularAcceleration,
                ),
            ))

        self.driveFeedforward = (
            wpimath.controller.SimpleMotorFeedforwardMeters(1, 3))
        self.turnFeedforward = (
            wpimath.controller.SimpleMotorFeedforwardMeters(1, 0.5))

        self.driveEncoder.setDistancePerPulse(
            math.tau * kWheelRadius / kEncoderResolution)
        self.turningEncoder.setDistancePerPulse(
            math.tau / kEncoderResolution)

        self.turningPIDController.enableContinuousInput(
            -math.pi, math.pi)

    def getState(self) -> wpimath.kinematics.SwerveModuleState:
        return wpimath.kinematics.SwerveModuleState(
            self.driveEncoder.getRate(),
            wpimath.geometry.Rotation2d(
                self.turningEncoder.getDistance()),
        )

    def getPosition(self) -> wpimath.kinematics.SwerveModulePosition:
        return wpimath.kinematics.SwerveModulePosition(
            self.driveEncoder.getDistance(),
            wpimath.geometry.Rotation2d(
                self.turningEncoder.getDistance()),
        )

    def setDesiredState(
        self, desiredState: wpimath.kinematics.SwerveModuleState
    ) -> None:
        encoderRotation = wpimath.geometry.Rotation2d(
            self.turningEncoder.getDistance())

        desiredState.optimize(encoderRotation)
        desiredState.cosineScale(encoderRotation)

        driveOutput = self.drivePIDController.calculate(
            self.driveEncoder.getRate(), desiredState.speed)
        driveFeedforward = self.driveFeedforward.calculate(
            desiredState.speed)

        turnOutput = self.turningPIDController.calculate(
            self.turningEncoder.getDistance(),
            desiredState.angle.radians())
        turnFeedforward = self.turnFeedforward.calculate(
            self.turningPIDController.getSetpoint().velocity)

        self.driveMotor.setVoltage(driveOutput + driveFeedforward)
        self.turningMotor.setVoltage(turnOutput + turnFeedforward)
