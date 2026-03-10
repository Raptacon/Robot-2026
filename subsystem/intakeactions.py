import logging
import time

import commands2
import rev
import wpilib
from ntcore.util import ntproperty

from constants import CaptainPlanetConsts as intakeConsts

logger = logging.getLogger(__name__)


class IntakeSubsystem(commands2.SubsystemBase):

    # Tunable roller speed — persistent so it survives reboots
    rollerVelocity = ntproperty("/subsystem/intake/rollerVelocity", 0.3,
                                writeDefault=False, persistent=True)

    # Read-only telemetry published every cycle via updateTelemetry()
    _nt_rollerPosition = ntproperty("/subsystem/intake/rollerPosition", 0.0)
    _nt_rollerEncoderVelocity = ntproperty("/subsystem/intake/rollerEncoderVelocity", 0.0)
    _nt_rollerCondition = ntproperty("/subsystem/intake/rollerCondition", 0)
    _nt_jamDetected = ntproperty("/subsystem/intake/jamDetected", False)

    def __init__(self, alternateConfiguration=False):
        logger.warning(
            "Intake CAN IDs (intake=%d, roller=%d) are placeholders — "
            "update CaptainPlanetConsts once hardware is wired",
            intakeConsts.kIntakeMotorCanId, intakeConsts.kRollerMotorCanId,
        )
        if alternateConfiguration:
            self.rollerMotor = rev.SparkFlex(
                intakeConsts.kIntakeMotorCanId,
                rev.SparkLowLevel.MotorType.kBrushless,
            )
        else:
            self.rollerMotor = rev.SparkMax(
                intakeConsts.kRollerMotorCanId,
                rev.SparkLowLevel.MotorType.kBrushless,
            )
        self.rollerMotorEncoder = self.rollerMotor.getEncoder()

        # Jam detection state
        self.rollerFaultThreshold = 2
        self.jamFaultThreshold = 0
        self.jamTime = 1
        self.jamThreshold = 10
        self.jamReversalTime = 3
        self.unjam = 1500

        self.baselineFault = 0
        self.baselineJam = 0
        self.jamReversalCount = 0
        self.jamOccurence = 0
        self.baselineDetectedJam = 0
        self.rollerSensor = 0
        self.rollerCondition = 0
        self.jamDetected = False

    def activateRoller(self):
        if self.rollerCondition != 1:
            self.rollerCondition = 1

    def deactivateRoller(self):
        if self.rollerCondition != 0:
            self.rollerCondition = 0

    def jamDetection(self):
        if not self.jamDetected:
            if (self.rollerMotorEncoder.getVelocity() <= self.jamThreshold
                    and self.rollerCondition == 1):
                if self.jamOccurence == 0:
                    self.baselineJam = time.perf_counter()
                    self.jamOccurence = 1
                else:
                    if time.perf_counter() - self.baselineJam >= self.jamTime:
                        self.baselineDetectedJam = time.perf_counter()
                        self.jamDetected = True
        else:
            if (time.perf_counter() - self.baselineDetectedJam
                    <= self.jamReversalTime and self.jamOccurence == 1):
                self.rollerCondition = -1
                if abs(self.rollerMotorEncoder.getVelocity()) >= self.unjam:
                    self.jamOccurence = 0
            else:
                if self.rollerMotorEncoder.getVelocity() <= self.unjam:
                    wpilib.Alert(
                        "Jam reversal unsuccessful! Stopping motor.",
                        wpilib.Alert.AlertType.kError,
                    )
                    self.rollerMotor.disable()
                self.rollerCondition = 1
                self.jamOccurence = 0
                self.jamDetected = False

    def updateRoller(self, newRollerVelocity):
        self.rollerVelocity = newRollerVelocity

    def motorChecks(self):
        self.rollerMotor.set(self.rollerCondition * self.rollerVelocity)

    def periodic(self):
        self.motorChecks()
        self.jamDetection()

    def updateTelemetry(self):
        """Publish intake state to NT (called by SubsystemRegistry)."""
        self._nt_rollerPosition = self.rollerMotorEncoder.getPosition()
        self._nt_rollerEncoderVelocity = self.rollerMotorEncoder.getVelocity()
        self._nt_rollerCondition = self.rollerCondition
        self._nt_jamDetected = self.jamDetected


# ---------------------------------------------------------------------------
# Self-registration
# ---------------------------------------------------------------------------
from utils.subsystem_factory import SubsystemState, register_subsystem

register_subsystem(
    name="intake",
    default_state=SubsystemState.enabled,
    creator=lambda subs: IntakeSubsystem(),
)
