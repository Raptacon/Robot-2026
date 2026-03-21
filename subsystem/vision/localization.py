import commands2
import wpilib
from wpilib import SmartDashboard, Field2d
import ntcore
import photonlibpy
from robotpy_apriltag import AprilTagFieldLayout, AprilTagField
import wpimath
from wpimath.geometry import Translation3d, Rotation3d
import math
from time import sleep


nt = ntcore.NetworkTableInstance.getDefault()


class Localization(commands2.Subsystem):


    def __init__(self):
        super().__init__()

        self.target_pose_back = wpimath.geometry.Pose3d( #I don't think we are using this anywhere
            Translation3d(0.0, 0.0, 0.0), #Set to the coordinates of apriltage #20
            Rotation3d.fromDegrees(0.0, 0.0, 0.0),
        )
        self.target_pose_front = wpimath.geometry.Pose3d( #I don't think we are using this anywhere
            Translation3d(0.0, 0.0, 0.0), #Set to the coordinates of apriltage #20
            Rotation3d.fromDegrees(0.0, 0.0, 0.0),
        )


    def periodic(self):
        if wpilib.DriverStation.isDisabled():
            return


    def robotInit(self):
        self.counter = nt.getTable("MyRobot").getEntry("Counter")
        self.counter.setInteger(0)
        #self.networkTargetX  = nt.getDoubleTopic("MyRobot").getEntry("targetX")
        self.new_target_pose = 0.0
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
        #print(nt.getTopics())
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

        self.tag_pose = wpimath.geometry.Pose3d( #I don't think we are using this anywhere
            Translation3d(5.23, 4.03, 1.12), #Set to the coordinates of apriltage #20
            Rotation3d.fromDegrees(0.0, 0.0, 0.0),
        )


    def teleopPeriodic(self):
        self.counter.setInteger(self.counter.getInteger(0) + 1)

        if wpilib.DriverStation.getAlliance() == wpilib.DriverStation.Alliance.kRed:
            self.target_pose = wpimath.geometry.Pose3d( #sets the position of the desired targeted pose
                Translation3d(4.625594, 4.034663, 1.8288), #Currently set the center point of the red hub
                Rotation3d.fromDegrees(0.0, 0.0, 0.0),
        )
        else:
            self.target_pose = wpimath.geometry.Pose3d( #sets the position of the desired targeted pose
                Translation3d(11.915394, 4.034663, 1.8288), #Currently set the center point of the red hub
                Rotation3d.fromDegrees(0.0, 0.0, 0.0),
        )
    
        self.field = Field2d()
        SmartDashboard.putData("Field", self.field) #Puts an image of the field into the SmartDashboard (from the wpilib library)
        # self.field.getObject("Target").setPose( #not sure what this does
        #     Pose2d(target_pose.X(), target_pose.Y(), 0.0)
        #)

        FrontPipe = self.camera.getAllUnreadResults()
        if len(FrontPipe) > 0: #If the camera sees an apriltag
            results_front = FrontPipe[-1]  # take the most recent result the camera had
            camEstPose = self.camPoseEst.estimateCoprocMultiTagPose(results_front)
            if camEstPose is None:
                camEstPose = self.camPoseEst.estimateLowestAmbiguityPose(results_front)
            if camEstPose is not None:
                self.target_pose_front = self.target_pose - camEstPose.estimatedPose #sets the new target pose based off where the robot is and where the previously defined pose is
                #self.networkTargetX.setFloat(self.target_pose_front.X()) #Adds to the network table the current position of the X on target pose

        BackPipe = self.camera2.getAllUnreadResults()
        if len(BackPipe) > 0: #If the camera sees an apriltag
            results_back = BackPipe[-1]  # take the most recent result the camera had
            camEstPose_Back = self.camPoseEst_Back.estimateCoprocMultiTagPose(results_back)
            if camEstPose_Back is None:
                camEstPose_Back = self.camPoseEst_Back.estimateLowestAmbiguityPose(results_back)
            if camEstPose_Back is not None:
                self.target_pose_back = self.target_pose - camEstPose_Back.estimatedPose #sets the new target pose based off where the robot is and where the previously defined pose is
                #self.networkTargetX.setFloat(self.target_pose_back.X()) #Adds to the network table the current position of the X on target pose

        if len(BackPipe) != 0 or len(FrontPipe) != 0:
            if len(BackPipe) == len(FrontPipe): #If both cameras see the same number of apriltags, it averages the two pose estimates
                sleep(0.001) #Delay to try and reduce freak-outs
                self.new_target_pose = (self.target_pose_front.X() + self.target_pose_back.X()) / 2 
                self.new_target_pose = math.degrees(self.new_target_pose) / 360 / 2 #Turns the X value into a degree value that the robot can read
    
            elif len(BackPipe) > len(FrontPipe): #If the back camera sees more apriltags than the front camera, it takes the pose estimate from the back camera
                sleep(0.001) #Delay to try and reduce freak-outs
                self.new_target_pose = self.target_pose_back
                self.new_target_pose = self.new_target_pose.X() #Takes only the X value of the target pose
                self.new_target_pose = math.degrees(self.new_target_pose) / 360 / 2 #Turns the X value into a degree value that the robot can read
        
            elif len(BackPipe) < len(FrontPipe): #If the front camera sees more apriltags than the back camera, it takes the pose estimate from the front camera
                sleep(0.001) #Delay to try and reduce freak-outs
                self.new_target_pose = self.target_pose_front
                self.new_target_pose = self.new_target_pose.X() #Takes only the X value of the target pose
                self.new_target_pose = math.degrees(self.new_target_pose) / 360 / 2 #Turns the X value into a degree value that the robot can read
                
        else:
            self.new_target_pose = 0.0


    def getTargetpose(self):

        return self.new_target_pose

"""
Code that might be helpful for improving the code in the future:

for result in results_back: #new code for multitag tracking, will be testing to see how it differs from the original code
            multitagResult = result.multitagResult
            if multitagResult is not None:
                fieldToCamera = multitagResult.estimatedPose.best
"""