import commands2
import wpilib
from wpilib import SmartDashboard, Field2d
import ntcore
import photonlibpy
from robotpy_apriltag import AprilTagFieldLayout, AprilTagField
import wpimath
from wpimath.geometry import Translation3d, Rotation3d
import math


nt = ntcore.NetworkTableInstance.getDefault()


class Localization(commands2.Subsystem):
    def __init__(self):
        super().__init__()

        self.target_pose_back = wpimath.geometry.Pose3d( #I don't think we are using this anywhere
            Translation3d(0.0, 0.0, 0.0),
            Rotation3d.fromDegrees(0.0, 0.0, 0.0),
        )
        self.target_pose_front = wpimath.geometry.Pose3d( #I don't think we are using this anywhere
            Translation3d(0.0, 0.0, 0.0), 
            Rotation3d.fromDegrees(0.0, 0.0, 0.0),
        )

        self._isDisabled = False

    def periodic(self):
        if wpilib.DriverStation.isDisabled():
            return

    def robotInit(self):
        self.counter = nt.getTable("MyRobot").getEntry("Counter")
        self.counter.setInteger(0)

        self.camera = photonlibpy.PhotonCamera("Front_Camera") #defines the camera according to how it's named on the photonvision website
        self.camera2 = photonlibpy.PhotonCamera("Back_Camera") #defines the camera according to how it's named on the photonvision website
