# Native imports
import wpilib
import ntcore
import photonlibpy
from typing import Callable

nt = ntcore.NetworkTableInstance.getDefault()
# nt.startClient3("Sim Robot")
# nt.setServer("localhost")


class Robot_Vision:
    """
    Container to hold the main vision code
    """

    def __init__(self, is_disabled: Callable[[], bool]) -> None:
        self.counter = nt.getTable("MyRobot").getEntry("Counter")
        self.counter.setInteger(0)
        print(nt.getTopics())
        self.camera = photonlibpy.PhotonCamera("Arducam_OV9281_USB_Camera")
        self.yawservo = wpilib.Servo(0)
        self.pitchservo = wpilib.Servo(1)
        self.yawservo_pos = 0.5
        self.pitchservo_pos = 0.5


    def robotPeriodic(self):
        pass
    def disabledInit(self):
        pass

    def disabledPeriodic(self):
        pass

    def autonomousInit(self):
        pass

    def autonomousPeriodic(self):
        pass

    def teleopInit(self):
        pass

    def teleopPeriodic(self):
        targetYaw = 0.0
        targetPitch = 0.0
        self.counter.setInteger(self.counter.getInteger(0) + 1)
        results = self.camera.getAllUnreadResults()
        if len(results) > 0:
            result = results[-1]  # take the most recent result the camera had
            for target in result.getTargets():
                if target.getFiducialId() == 19:
                    targetYaw = target.getYaw() / 360 / 2
                    targetPitch = target.getPitch() / 360 / 2
                print(target.getFiducialId())
    
        self.yawservo_pos -= targetYaw
        self.pitchservo_pos += targetPitch
        self.yawservo.set(self.yawservo_pos)
        self.pitchservo.set(self.pitchservo_pos)



    def testInit(self):
        pass
    def testPeriodic(self):
        pass

    def getDeployInfo(self, key: str) -> str:
        pass

    def setAlignmentTag(self, alignmentTagId: int | None) -> None:
        pass