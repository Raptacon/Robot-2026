import wpilib
import ntcore
import photonlibpy
from robotpy_apriltag import AprilTagFieldLayout, AprilTagField
from typing import Callable
import wpimath
import math

nt = ntcore.NetworkTableInstance.getDefault()

class MyRobot(wpilib.TimedRobot):
    def robotInit(self): 
        self.counter = nt.getTable("MyRobot").getEntry("Counter")
        self.counter.setInteger(0)
        field = AprilTagFieldLayout.loadField(AprilTagField.kDefaultField)
        kRobotToCam = wpimath.geometry.Transform3d(
            wpimath.geometry.Translation3d(0.5, 0.0, 0.5),
            wpimath.geometry.Rotation3d.fromDegrees(0.0, -30.0, 0.0),
        )
        self.camPoseEst = photonlibpy.PhotonPoseEstimator(field,kRobotToCam,)
        print(nt.getTopics())
        self.camera = photonlibpy.PhotonCamera("Arducam_OV9281_USB_Camera")
        self.yawservo = wpilib.Servo(0)
        self.pitchservo = wpilib.Servo(1)
        self.yawservo_pos = 0.5
        self.pitchservo_pos = 0.5

    def teleopPeriodic(self):
        targetYaw = 0.0
        targetPitch = 0.0
        self.counter.setInteger(self.counter.getInteger(0) + 1)
        results = self.camera.getAllUnreadResults()
        if len(results) > 0: 
            result = results[-1]  # take the most recent result the camera had
            for target in result.getTargets():
                if target.getFiducialId() == 20: 
                    targetYaw = target.getYaw()   / 360 / 2
                    targetPitch = target.getPitch() / 360 / 2
                print(target.getFiducialId())
                
                pose = target.getBestCameraToTarget()
                print(pose)
                print(targetYaw)
                print(targetPitch)

        if abs(targetYaw) < 0.005: #eliminates overcorrection
            targetYaw = 0.0
        if abs(targetPitch) < 0.005:
            targetPitch = 0.0
        
        self.yawservo_pos -= targetYaw
        self.pitchservo_pos += targetPitch
        self.yawservo.set(self.yawservo_pos)
        self.pitchservo.set(self.pitchservo_pos)
        
        #if(not math.isclose(targetYaw, self.yawservo_pos, abs_tol= 0.2)): #10 percent error
        #if(not math.isclose(targetPitch, self.pitchservo_pos, abs_tol = 0.1)):
        
