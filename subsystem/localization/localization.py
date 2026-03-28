"""
Vision-based localization subsystem using PhotonVision AprilTags.

Processes camera results from one or more PhotonVision cameras, filters
bad estimates, computes dynamic standard deviations, and feeds vision
poses into the drivetrain's SwerveDrive4PoseEstimator.

See VISION.md in this directory for best practices and tuning guidance.
"""

import math
from typing import List, Tuple

import wpilib
from wpimath.geometry import (
    Pose3d, Rotation3d, Transform3d, Translation3d,
)
from robotpy_apriltag import AprilTagField, AprilTagFieldLayout
import photonlibpy

from config import OperatorRobotConfig

# FRC field dimensions (meters) -- standard for 2024+ fields
FIELD_LENGTH_M = 16.54
FIELD_WIDTH_M = 8.21


class VisionCamera:
    """Wraps a single PhotonVision camera and its pose estimator."""

    def __init__(
        self,
        name: str,
        robot_to_camera: Transform3d,
        field_layout: AprilTagFieldLayout,
    ):
        self.name = name
        self.camera = photonlibpy.PhotonCamera(name)
        self.pose_estimator = photonlibpy.PhotonPoseEstimator(
            field_layout, robot_to_camera
        )


class Localization:
    """
    Processes PhotonVision AprilTag detections from multiple cameras and
    feeds filtered, weighted pose estimates into the drivetrain's pose
    estimator.

    This is not a commands2.Subsystem because it does not own any hardware
    actuators and does not need default commands. It is called from
    robotPeriodic() to update the drivetrain pose every cycle in all modes.
    """

    def __init__(self, drivetrain):
        """
        Args:
            drivetrain: SwerveDrivetrain instance that owns the pose estimator.
        """
        self.drivetrain = drivetrain
        self.field_layout = AprilTagFieldLayout.loadField(
            AprilTagField.kDefaultField
        )

        cfg = OperatorRobotConfig

        self.cameras: List[VisionCamera] = []
        self._add_camera(
            cfg.back_cam_name,
            cfg.back_cam_translation,
            cfg.back_cam_rotation_deg,
        )
        self._add_camera(
            cfg.side_cam_name,
            cfg.side_cam_translation,
            cfg.side_cam_rotation_deg,
        )

        # Filtering thresholds
        self.ambiguity_threshold = cfg.vision_ambiguity_threshold
        self.single_tag_max_dist = cfg.vision_single_tag_max_distance_m
        self.field_border_margin = cfg.vision_field_border_margin_m
        self.max_z_error = cfg.vision_max_z_error_m
        self.max_rotation_error_rad = math.radians(
            cfg.vision_max_rotation_error_deg
        )

        # Std dev bases
        self.single_tag_std_devs = cfg.vision_single_tag_std_devs
        self.multi_tag_std_devs = cfg.vision_multi_tag_std_devs
        self.std_dev_distance_factor = cfg.vision_std_dev_distance_factor

        # Telemetry
        self._nt_table = wpilib.SmartDashboard
        self._accepted_count = 0
        self._rejected_count = 0

    def _add_camera(
        self,
        name: str,
        translation: Tuple[float, float, float],
        rotation_deg: Tuple[float, float, float],
    ) -> None:
        robot_to_camera = Transform3d(
            Translation3d(*translation),
            Rotation3d.fromDegrees(*rotation_deg),
        )
        self.cameras.append(
            VisionCamera(name, robot_to_camera, self.field_layout)
        )

    def update(self) -> None:
        """Process all camera results and feed valid estimates to the drivetrain.

        Call this once per robot loop (from robotPeriodic).
        """
        for cam in self.cameras:
            if not cam.camera.isConnected():
                continue

            for result in cam.camera.getAllUnreadResults():
                self._process_result(cam, result)

        self._nt_table.putNumber(
            "Vision/accepted_count", self._accepted_count
        )
        self._nt_table.putNumber(
            "Vision/rejected_count", self._rejected_count
        )

    def _process_result(self, cam: VisionCamera, result) -> None:
        """Try multi-tag first, fall back to single-tag lowest ambiguity."""
        pose_est = cam.pose_estimator.estimateCoprocMultiTagPose(result)
        is_multi_tag = pose_est is not None

        if pose_est is None:
            pose_est = cam.pose_estimator.estimateLowestAmbiguityPose(result)

        if pose_est is None:
            return

        estimated_pose_3d: Pose3d = pose_est.estimatedPose
        targets_used = pose_est.targetsUsed
        timestamp = pose_est.timestampSeconds

        # --- Filtering ---
        if not self._passes_filters(
            estimated_pose_3d, targets_used, is_multi_tag
        ):
            self._rejected_count += 1
            return

        # --- Dynamic standard deviations ---
        std_devs = self._compute_std_devs(estimated_pose_3d, targets_used)

        # If all std devs are infinite, skip (fully rejected by distance)
        if all(s == float('inf') for s in std_devs):
            self._rejected_count += 1
            return

        self._accepted_count += 1
        self.drivetrain.add_vision_pose_estimate(
            estimated_pose_3d.toPose2d(), timestamp, std_devs
        )

    def _passes_filters(
        self,
        pose_3d: Pose3d,
        targets: list,
        is_multi_tag: bool,
    ) -> bool:
        """Return True if the estimate passes all quality filters."""
        pose_2d = pose_3d.toPose2d()

        # Field bounds check
        margin = self.field_border_margin
        x = pose_2d.X()
        y = pose_2d.Y()
        if (
            x < -margin
            or x > FIELD_LENGTH_M + margin
            or y < -margin
            or y > FIELD_WIDTH_M + margin
        ):
            return False

        # Z-height sanity check (robot should be on the carpet)
        if abs(pose_3d.Z()) > self.max_z_error:
            return False

        # Single-tag ambiguity check
        if not is_multi_tag and len(targets) == 1:
            if targets[0].poseAmbiguity > self.ambiguity_threshold:
                return False

        # Rotation agreement with gyro
        gyro_heading = self.drivetrain.current_yaw()
        vision_heading = pose_2d.rotation()
        rotation_diff = abs(
            (vision_heading - gyro_heading).radians()
        )
        # Normalize to [0, pi]
        rotation_diff = abs(
            math.atan2(math.sin(rotation_diff), math.cos(rotation_diff))
        )
        if rotation_diff > self.max_rotation_error_rad:
            return False

        return True

    def _compute_std_devs(
        self,
        estimated_pose: Pose3d,
        targets: list,
    ) -> Tuple[float, float, float]:
        """Compute dynamic standard deviations based on tag count and distance."""
        num_tags = 0
        total_dist = 0.0

        for target in targets:
            tag_pose = self.field_layout.getTagPose(target.fiducialId)
            if tag_pose is None:
                continue
            num_tags += 1
            total_dist += (
                tag_pose.toPose2d().translation().distance(
                    estimated_pose.toPose2d().translation()
                )
            )

        if num_tags == 0:
            return self.single_tag_std_devs

        avg_dist = total_dist / num_tags

        if num_tags > 1:
            base = self.multi_tag_std_devs
        else:
            base = self.single_tag_std_devs

        # Single tag beyond max distance: reject entirely
        if num_tags == 1 and avg_dist > self.single_tag_max_dist:
            return (float('inf'), float('inf'), float('inf'))

        # Scale std devs quadratically with distance
        scale = 1.0 + (avg_dist ** 2 / self.std_dev_distance_factor)
        return tuple(s * scale for s in base)

    def updateTelemetry(self) -> None:
        """Called by subsystem registry if this is registered as a subsystem."""
        pass
