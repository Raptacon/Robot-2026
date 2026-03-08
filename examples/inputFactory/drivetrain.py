#
# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.
#
# Based on the WPILib SwerveBot example:
# https://github.com/robotpy/examples/tree/main/SwerveBot
#
# Modified to be a commands2 Subsystem that accepts ManagedAnalog
# callables and supports swapping axis assignments at runtime.
#

import math
from typing import Callable

import commands2
import wpilib
import wpimath.geometry
import wpimath.kinematics
import swervemodule

kMaxSpeed = 3.0  # meters per second
kMaxAngularSpeed = math.pi  # 1/2 rotation per second


class Drivetrain(commands2.Subsystem):
    """Swerve drivetrain subsystem.

    Accepts axis callables (e.g. ManagedAnalog objects) for forward,
    strafe, and rotate.  The swap_axes() method exchanges the
    forward/rotate sources to demonstrate runtime axis remapping.
    """

    def __init__(
        self,
        forward: Callable[[], float],
        strafe: Callable[[], float],
        rotate: Callable[[], float],
    ) -> None:
        super().__init__()

        # Axis callables — swappable at runtime
        self._forward = forward
        self._strafe = strafe
        self._rotate = rotate
        self._swapped = False

        # Swerve hardware
        self.frontLeftLocation = wpimath.geometry.Translation2d(
            0.381, 0.381)
        self.frontRightLocation = wpimath.geometry.Translation2d(
            0.381, -0.381)
        self.backLeftLocation = wpimath.geometry.Translation2d(
            -0.381, 0.381)
        self.backRightLocation = wpimath.geometry.Translation2d(
            -0.381, -0.381)

        self.frontLeft = swervemodule.SwerveModule(
            1, 2, 0, 1, 2, 3)
        self.frontRight = swervemodule.SwerveModule(
            3, 4, 4, 5, 6, 7)
        self.backLeft = swervemodule.SwerveModule(
            5, 6, 8, 9, 10, 11)
        self.backRight = swervemodule.SwerveModule(
            7, 8, 12, 13, 14, 15)

        self.gyro = wpilib.AnalogGyro(0)

        self.kinematics = wpimath.kinematics.SwerveDrive4Kinematics(
            self.frontLeftLocation,
            self.frontRightLocation,
            self.backLeftLocation,
            self.backRightLocation,
        )

        self.odometry = wpimath.kinematics.SwerveDrive4Odometry(
            self.kinematics,
            self.gyro.getRotation2d(),
            (
                self.frontLeft.getPosition(),
                self.frontRight.getPosition(),
                self.backLeft.getPosition(),
                self.backRight.getPosition(),
            ),
        )

        self.gyro.reset()

    # --- Axis swapping ---

    @property
    def isSwapped(self) -> bool:
        return self._swapped

    def swap_axes(self) -> None:
        """Toggle between normal and swapped axis layout.

        Normal:  forward=left_stick_y, rotate=right_stick_x
        Swapped: forward=right_stick_x, rotate=left_stick_y
        """
        self._forward, self._rotate = self._rotate, self._forward
        self._swapped = not self._swapped
        wpilib.SmartDashboard.putBoolean(
            "Axes Swapped", self._swapped)

    def swapAxesCommand(self) -> commands2.Command:
        """Return an InstantCommand that toggles axis layout."""
        return commands2.InstantCommand(
            self.swap_axes).withName("Swap Axes")

    # --- Driving ---

    def drive(
        self,
        xSpeed: float,
        ySpeed: float,
        rot: float,
        fieldRelative: bool,
        periodSeconds: float,
    ) -> None:
        """Drive the robot.

        :param xSpeed: Speed in the x direction (forward).
        :param ySpeed: Speed in the y direction (sideways).
        :param rot: Angular rate of the robot.
        :param fieldRelative: Whether speeds are field-relative.
        :param periodSeconds: Time period.
        """
        swerveModuleStates = self.kinematics.toSwerveModuleStates(
            wpimath.kinematics.ChassisSpeeds.discretize(
                (
                    wpimath.kinematics.ChassisSpeeds
                    .fromFieldRelativeSpeeds(
                        xSpeed, ySpeed, rot,
                        self.gyro.getRotation2d())
                    if fieldRelative
                    else wpimath.kinematics.ChassisSpeeds(
                        xSpeed, ySpeed, rot)
                ),
                periodSeconds,
            )
        )
        wpimath.kinematics.SwerveDrive4Kinematics \
            .desaturateWheelSpeeds(swerveModuleStates, kMaxSpeed)
        self.frontLeft.setDesiredState(swerveModuleStates[0])
        self.frontRight.setDesiredState(swerveModuleStates[1])
        self.backLeft.setDesiredState(swerveModuleStates[2])
        self.backRight.setDesiredState(swerveModuleStates[3])

    def updateOdometry(self) -> None:
        """Updates the field relative position of the robot."""
        self.odometry.update(
            self.gyro.getRotation2d(),
            (
                self.frontLeft.getPosition(),
                self.frontRight.getPosition(),
                self.backLeft.getPosition(),
                self.backRight.getPosition(),
            ),
        )

    # --- Default command factory ---

    def defaultDriveCommand(
        self,
        fieldRelative: bool = True,
    ) -> commands2.Command:
        """Create the default drive command.

        Reads the subsystem's stored axis callables each cycle.
        The axis swap toggle changes which callables provide
        forward vs rotate, so the default command doesn't need
        to know about the swap — it just reads the current
        callables.

        This is a RunCommand (runs every cycle until interrupted),
        intended to be set as the subsystem's default command.
        """
        def _drive():
            self.drive(
                self._forward(),
                self._strafe(),
                self._rotate(),
                fieldRelative,
                0.02,  # 20ms period
            )

        cmd = commands2.RunCommand(_drive, self)
        cmd.setName("DefaultDrive")
        return cmd
