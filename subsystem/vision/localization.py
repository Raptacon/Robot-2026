import commands2
import wpilib
from wpilib import SmartDashboard, Field2d
import ntcore
import photonlibpy
from robotpy_apriltag import AprilTagFieldLayout, AprilTagField
import wpimath
from wpimath.geometry import Translation3d, Rotation3d

nt = ntcore.NetworkTableInstance.getDefault()

class Localization(commands2.Subsystem):

    def __int__(self):
        super().__init__()
        self.target_pose_front = 0

    def periodic(self):
        if wpilib.DriverStation.isDisabled():
            return

    def robotInit(self): 
        self.counter = nt.getTable("MyRobot").getEntry("Counter")
        self.counter.setInteger(0)
        self.networkTargetX  = nt.getDoubleTopic("MyRobot").getEntry("targetX")
        self.new_target_pose = 0
        #self.networkTargetX_Back = nt.getTable("MyRobot").getEntry("targetX_Back")
        field = AprilTagFieldLayout.loadField(AprilTagField.kDefaultField)
        Camera_Front_ToRobot = wpimath.geometry.Transform3d( #Sets the offset for the center of the robot to targeted cam
            Translation3d(0.0, 0.0, 0.0), #Translation3d comes from wpilib.geometry
            Rotation3d.fromDegrees(0.0, 0.0, 0.0), #Rotation3d comes from wpilib.geometry
        )
        Camera_Back_ToRobot = wpimath.geometry.Transform3d( #Sets the offset for the center of the robot to targeted cam
            Translation3d(0.0, 0.0, 0.0), #Translation3d comes from wpilib.geometry
            Rotation3d.fromDegrees(0.0, 0.0, 0.0), #Rotation3d comes from wpilib.geometry
        )
        self.camPoseEst = photonlibpy.PhotonPoseEstimator(field,Camera_Front_ToRobot) #Sets the estimated pose based off the field layout and the robot to camera position?/Potentially simplifies both cameras into one pose estimate
        self.camPoseEst_Back = photonlibpy.PhotonPoseEstimator(field,Camera_Back_ToRobot) #Sets the estimated pose based off the field layout and the robot to camera position?
        print(nt.getTopics())
        self.camera = photonlibpy.PhotonCamera("Front_Camera") #defines the camera according to how it's named on the photonvision website
        self.camera2 = photonlibpy.PhotonCamera("Back_Camera") #defines the camera according to how it's named on the photonvision website
        """
        We will have to change variable names to match up to what we will actually call the cameras. Also,

        !!!IMPORTANT!!!:
        When plugging the camera into the pi, make sure you plug the camera into the same spot everytime! If you
        do not do this, it will switch cameras around and our offset for the cameras will be wrong. If you plug
        the first camera into the first slot, plug it in that slot every time. I don't know
        why it does this, but it does. (Ignore this if this issue has been fixed/isn't a problem anymore)
        """
        self.target_pose = wpimath.geometry.Pose3d( #sets the position of the desired targeted pose
            Translation3d(4.625594, 4.034663, 1.8288), #Currently set the center point of the red hub
            Rotation3d.fromDegrees(0.0, 0.0, 0.0),
        )
        self.tag_pose = wpimath.geometry.Pose3d( #I don't think we are using this anywhere
            Translation3d(5.23, 4.03, 1.12), #Set to the coordinates of apriltage #20
            Rotation3d.fromDegrees(0.0, 0.0, 0.0),
        )

    def teleopPeriodic(self):
        self.counter.setInteger(self.counter.getInteger(0) + 1)
        
        results_front = self.camera.getAllUnreadResults(), self.camera.getAllUnreadResults()
        if len(results_front) > 0: #If the camera sees an apriltag
            #results_front = results_front[-1]  # take the most recent result the camera had
            camEstPose = self.camPoseEst.estimateCoprocMultiTagPose(results_front)
            if camEstPose is None:
                camEstPose = self.camPoseEst.estimateLowestAmbiguityPose(results_front)
            if camEstPose is not None:
                self.target_pose_front = self.target_pose - camEstPose.estimatedPose #sets the new target pose based off where the robot is and where the previously definded pose is
                #self.networkTargetX.setFloat(self.target_pose_front.X()) #Adds to the network table the current position of the X on target pose

        self.field = Field2d()
        SmartDashboard.putData("Field", self.field) #Puts an image of the field into the SmartDashboard (from the wpilib library)
        # self.field.getObject("Target").setPose( #not sure what this does
        #     Pose2d(target_pose.X(), target_pose.Y(), 0.0)
        #)

        results_back = self.camera2.getAllUnreadResults()
        if len(results_back) > 0: #If the camera sees an apriltag
            #results_back = results_back[-1]  # take the most recent result the camera had
            camEstPose_Back = self.camPoseEst_Back.estimateCoprocMultiTagPose(results_back)
            if camEstPose_Back is None:
                camEstPose_Back = self.camPoseEst_Back.estimateLowestAmbiguityPose(results_back)
            if camEstPose_Back is not None:
                target_pose_back = self.target_pose - camEstPose_Back.estimatedPose #sets the new target pose based off where the robot is and where the previously definded pose is
                #self.networkTargetX.setFloat(self.target_pose_back.X()) #Adds to the network table the current position of the X on target pose

        # for result in results_back: #new code for multitag tracking, will be testing to see how it differs from the orignal code
        #     multitagResult = result.multitagResult
        #     if multitagResult is not None: 
        #         fieldToCamera = multitagResult.estimatedPose.best 
        #         print(str(fieldToCamera))

        if len(results_back) != 0 or len(results_front) != 0:
            if len(results_back) == len(results_front): #If both cameras see the same number of apriltags, it averages the two pose estimates
                self.new_target_pose = (self.target_pose_front + target_pose_back) / 2
            
            elif len(results_back) > len(results_front): #If the back camera sees more apriltags than the front camera, it takes the pose estimate from the back camera
                self.new_target_pose = target_pose_back 
            
            elif len(results_back) < len(results_front): #If the front camera sees more apriltags than the back camera, it takes the pose estimate from the front camera
                self.new_target_pose = self.target_pose_front
                print(str(self.new_target_pose))
        else:
            self.new_target_pose = 0

    def getTargetpose(self):
        return float(self.new_target_pose)