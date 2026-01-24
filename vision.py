from typing import Callable, List, Optional, Tuple

from wpilib import SmartDashboard
from wpimath.geometry import Pose2d, Transform3d, Rotation3d, Translation3d
from photonlibpy import PhotonCamera, PhotonPoseEstimator
from photonlibpy.targeting import PhotonPipelineResult, PhotonTrackedTarget
from robotpy_apriltag import AprilTagField, AprilTagFieldLayout

from config import OperatorRobotConfig
from subsystem.drivetrain.swerve_drivetrain import SwerveDrivetrain


class Vision:
    def __init__(
        self, driveTrain: SwerveDrivetrain,
        left_cam_name: str = "Blue_Port_Left_Side",
        right_cam_name: str = "Side_Port_Right_Side"
    ):
        self.cameras = [PhotonCamera(left_cam_name), PhotonCamera(right_cam_name)]
        self.drive = driveTrain
        self.field_layout = AprilTagFieldLayout.loadField(AprilTagField.k2025ReefscapeWelded)

        self.cameraPoseEstimators = [
            PhotonPoseEstimator(
                self.field_layout,
                Transform3d(Translation3d(*camToRobotTranslation), Rotation3d.fromDegrees(*camToRobotRotation))
            )
            for camera, camToRobotTranslation, camToRobotRotation in zip(
                self.cameras,
                [OperatorRobotConfig.robot_Cam_Translation_Left, OperatorRobotConfig.robot_Cam_Translation_Right],
                [OperatorRobotConfig.robot_Cam_Rotation_Degress_Left, OperatorRobotConfig.robot_Cam_Rotation_Degress_Right]
            )
        ]

        self.cameraPipelineResults = [[] for _ in range(len(self.cameras))] # avoid memory copy
        self.cameraPoseEstimates = [None] * len(self.cameras)

    def getSingleCamPipelineResult(self, camera: PhotonCamera, cameraIndex: int) -> List[PhotonPipelineResult]:
        latestPipelineResults = []
        unreadResults = camera.getAllUnreadResults()
        if unreadResults is not None:
            latestPipelineResults = unreadResults
        return latestPipelineResults

    def getSingleCamEstimate(
        self, unreadCameraPipelines: List[PhotonPipelineResult], poseEstimator: PhotonPoseEstimator, specificTagId: int | None = None
    ) -> Pose2d | None:
        poseEstimate = None
        validTagIds = self.reef_tag_ids
        if specificTagId is not None:
            validTagIds = {specificTagId}

        if not ((len(unreadCameraPipelines) == 0) or (poseEstimator is None)):
            bestPipeline = unreadCameraPipelines[-1]
            targetsKeep = [
                target
                for target in bestPipeline.getTargets()
                if (
                    (target is not None)
                    and (target.getFiducialId() in validTagIds)
                    and (target.getPoseAmbiguity() < OperatorRobotConfig.vision_ambiguity_threshold)
                    and (target.getBestCameraToTarget().translation().norm() < OperatorRobotConfig.vision_distance_threshold_m)
                )
            ]

            if len(targetsKeep) > 0:
                filteredPipeline = PhotonPipelineResult(
                    bestPipeline.ntReceiveTimestampMicros, targetsKeep, bestPipeline.metadata
                )
                camEstPose = poseEstimator.update(filteredPipeline)

                if camEstPose:
                    targetDistances = [
                        target.getBestCameraToTarget().translation().norm() for target in filteredPipeline.getTargets()
                    ]

                    if len(targetDistances) > 0:
                        distanceToClosestTarget = min(targetDistances)
                        stdDev = self.distanceToStdDev(distanceToClosestTarget)
                        poseEstimate = camEstPose.estimatedPose.toPose2d()
                        self.drive.add_vision_pose_estimate(
                            poseEstimate, camEstPose.timestampSeconds, stdDev
                        )
        return poseEstimate

    def getCamEstimates(self, specificTagId: Optional[Callable[[], int]] = None) -> None:
        for i, camera, cameraPoseEstimator in zip(range(len(self.cameras)), self.cameras, self.cameraPoseEstimators):
            latestPipelineResults = self.getSingleCamPipelineResult(camera, i)
            self.cameraPipelineResults[i] = latestPipelineResults
            poseEstimate = self.getSingleCamEstimate(latestPipelineResults, cameraPoseEstimator, specificTagId=specificTagId())
            self.cameraPoseEstimates[i] = poseEstimate

    def getTargetDataForPrint(self, target: PhotonTrackedTarget) -> Tuple[float]:
        """
        Only use this method to retrieve values for print statements
        """
        if target is None:
            targetID, targetYaw, targetPitch, targetAmbiguity = (0, 0, 0, 0)
        else:
            targetID = target.getFiducialId()
            targetYaw = target.getYaw()
            targetPitch = target.getPitch()
            targetAmbiguity = target.getPoseAmbiguity()
        return targetID, targetYaw, targetPitch, targetAmbiguity

    def showTargetData(self, target: Optional[PhotonTrackedTarget] = None):
        if target is None:
            somePipelineResults = self.cameraPipelineResults[0]
            if len(somePipelineResults) > 0:
                target = somePipelineResults[0].getBestTarget()

        if target is None:
            return

        targetID, targetYaw, targetPitch, targetAmbiguity = self.getTargetDataForPrint(target)

        SmartDashboard.putNumber("Target ID", targetID)
        SmartDashboard.putNumber("Target Yaw", targetYaw)
        SmartDashboard.putNumber("Target Pitch", targetPitch)
        SmartDashboard.putNumber("Target Ambiguity", targetAmbiguity)

    def distanceToStdDev(self, distance: float | None) -> Tuple[float]:
        std_dev = OperatorRobotConfig.vision_default_std_dev
        if distance:
            if distance > OperatorRobotConfig.vision_distance_threshold_m:
                # Ignore vision if too far away from tag
                std_dev = 10000
            else:
                std_dev = -1 + (OperatorRobotConfig.vision_std_dev_basis)**(OperatorRobotConfig.vision_std_dev_scale_factor * distance)
        return (std_dev, std_dev, std_dev * 2)
