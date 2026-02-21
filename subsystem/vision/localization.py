import commands2
import wpilib
from wpilib import SmartDashboard, Field2d
import ntcore
import photonlibpy
from robotpy_apriltag import AprilTagFieldLayout, AprilTagField
import wpimath
from wpimath.geometry import Pose2d, Translation3d, Rotation3d

nt = ntcore.NetworkTableInstance.getDefault()

class Localization(commands2.Subsystem):

    def __int__(self):
        super().__init__()

    def periodic(self):
        if wpilib.DriverStation.isDisabled():
            return

    def robotInit(self): 
        self.counter = nt.getTable("MyRobot").getEntry("Counter")
        self.counter.setInteger(0)
        self.networkTargetX = nt.getTable("MyRobot").getEntry("targetX")
        field = AprilTagFieldLayout.loadField(AprilTagField.kDefaultField)
        kRobotToCam = wpimath.geometry.Transform3d( #Sets the offset for the center of the robot to targeted cam
            Translation3d(0.0, 0.0, 0.0), #Translation3d comes from wpilib.geometry
            Rotation3d.fromDegrees(0.0, 0.0, 0.0), #Rotation3d comes from wpilib.geometry
        )
        self.camPoseEst = photonlibpy.PhotonPoseEstimator(field,kRobotToCam,) #Sets the estimated pose based off the field layout and the robot to camera position?
        print(nt.getTopics())
        self.camera = photonlibpy.PhotonCamera("Arducam_OV9281_USB_Camera") #defines the camera according to how it's named on the photonvision website
        self.target_pose = wpimath.geometry.Pose3d( #sets the position of the desired targeted pose
            Translation3d(4.625594, 4.034663, 1.8288), #Currently set the center point of the blue hub
            Rotation3d.fromDegrees(0.0, 0.0, 0.0),
        )
        self.tag_pose = wpimath.geometry.Pose3d( #I don't think we are using this anywhere
            Translation3d(5.23, 4.03, 1.12), #Set to the coordinates of apriltage #20
            Rotation3d.fromDegrees(0.0, 0.0, 0.0),
        )
        self.field = Field2d()
        SmartDashboard.putData("Field", self.field) #Puts an image of the field into the SmartDashboard (from the wpilib library)
        self.field.getObject("Target").setPose( #not sure what this does
            Pose2d(4.655, 4.019, 0.0)
        )

    def teleopPeriodic(self):
        self.counter.setInteger(self.counter.getInteger(0) + 1)
        
        results = self.camera.getAllUnreadResults()
        if len(results) > 0: 
            result = results[-1]  # take the most recent result the camera had
            camEstPose = self.camPoseEst.estimateCoprocMultiTagPose(result)
            if camEstPose is None:
                camEstPose = self.camPoseEst.estimateLowestAmbiguityPose(result)
            if camEstPose is not None:
                target_pose = self.target_pose - camEstPose.estimatedPose #sets the new target pose based off where the robot is and where the previously definded pose is
                self.networkTargetX.setFloat(target_pose.X()) #Adds to the network table the current position of the X on target pose
