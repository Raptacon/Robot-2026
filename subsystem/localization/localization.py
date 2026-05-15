"""
Vision-based localization subsystem using PhotonVision AprilTags.

Processes camera results from one or more PhotonVision cameras, filters
bad estimates, computes dynamic standard deviations, and feeds vision
poses into the drivetrain's SwerveDrive4PoseEstimator.

On hardware, uses a ctypes-based fast deserializer (fast_photon_reader.py)
that bypasses photonlibpy's slow Python-level struct.unpack calls. In
simulation, falls back to photonlibpy's PhotonCamera + VisionSystemSim
since sim performance is not constrained.

See VISION.md in this directory for best practices and tuning guidance.
"""

import math
from typing import Dict, List, Optional, Tuple

import ntcore
import wpilib
from wpimath.geometry import (
    Pose2d, Pose3d, Transform3d, Translation2d,
)
from robotpy_apriltag import AprilTagField, AprilTagFieldLayout

from constants.robot_geometry import CAMERAS
from config import OperatorRobotConfig

# FRC field dimensions (meters) -- standard for 2024+ fields
FIELD_LENGTH_M = 16.54
FIELD_WIDTH_M = 8.21


class VisionCamera:
    """Wraps a single PhotonVision camera with fast or sim-mode readers."""

    def __init__(
        self,
        name: str,
        robot_to_camera: Transform3d,
        field_layout: AprilTagFieldLayout,
        use_fast_reader: bool,
    ):
        self.name = name
        self.robot_to_camera = robot_to_camera

        if use_fast_reader:
            from .fast_photon_reader import FastPhotonSubscriber
            self.fast_sub = FastPhotonSubscriber(name, robot_to_camera)
            self.photon_camera = None
            self.pose_estimator = None
        else:
            import photonlibpy
            self.fast_sub = None
            self.photon_camera = photonlibpy.PhotonCamera(name)
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

    def __init__(self, drivetrain, field=None):
        """
        Args:
            drivetrain: SwerveDrivetrain instance that owns the pose estimator.
            field: Optional Field2d to publish detected tag markers onto.
        """
        self.drivetrain = drivetrain
        self.field_layout = AprilTagFieldLayout.loadField(
            AprilTagField.kDefaultField
        )

        cfg = OperatorRobotConfig

        # Use fast ctypes reader on hardware, photonlibpy in sim
        self._use_fast_reader = not wpilib.RobotBase.isSimulation()

        self.cameras: List[VisionCamera] = []
        for cam_geo in CAMERAS:
            self._add_camera_from_geometry(cam_geo)

        # Cache tag poses at init to avoid repeated lookups in hot loops
        self._tag_pose_cache: Dict[int, Pose3d] = {}
        self._tag_translation_cache: Dict[int, Translation2d] = {}
        for tag_id in range(1, 23):
            pose = self.field_layout.getTagPose(tag_id)
            if pose is not None:
                self._tag_pose_cache[tag_id] = pose
                self._tag_translation_cache[tag_id] = (
                    pose.toPose2d().translation()
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

        # Telemetry via NT struct publishers (for AdvantageScope)
        nt = ntcore.NetworkTableInstance.getDefault()
        self._nt_vision = nt.getTable("Vision")
        self._accepted_count = 0
        self._rejected_count = 0
        self._detected_tag_ids: List[int] = []
        self._detected_tag_poses: List[Pose2d] = []
        self._field = field

        # Struct publishers for native AdvantageScope drag-and-drop
        self._accepted_pose_pub = nt.getStructTopic(
            "Vision/acceptedPose", Pose2d
        ).publish()
        self._detected_tags_pub = nt.getStructArrayTopic(
            "Vision/detectedTagPoses", Pose3d
        ).publish()

    def _add_camera_from_geometry(self, cam_geo) -> None:
        """Create a VisionCamera from a CameraGeometry definition."""
        self.cameras.append(
            VisionCamera(
                cam_geo.name, cam_geo.robot_to_camera, self.field_layout,
                self._use_fast_reader,
            )
        )

    # ── Main update loop ───────────────────────────────────────────────

    def update(self) -> None:
        """Process all camera results and feed valid estimates to the drivetrain.

        Call this once per robot loop (from robotPeriodic).
        """
        self._detected_tag_ids.clear()
        self._detected_tag_poses.clear()
        had_results = False

        if self._use_fast_reader:
            had_results = self._update_fast()
        else:
            had_results = self._update_sim()

        # Only publish telemetry when new results were processed
        if had_results:
            self._nt_vision.putNumber(
                "accepted_count", self._accepted_count
            )
            self._nt_vision.putNumber(
                "rejected_count", self._rejected_count
            )
            self._nt_vision.putNumberArray(
                "detected_tag_ids", self._detected_tag_ids
            )

            # Detected tag poses as struct array (AdvantageScope 3D field)
            tag_poses_3d = [
                self._tag_pose_cache[tid]
                for tid in self._detected_tag_ids
                if tid in self._tag_pose_cache
            ]
            self._detected_tags_pub.set(tag_poses_3d)

            # Field2d 2D view (sim GUI)
            if self._field is not None:
                self._field.getObject("Detected Tags").setPoses(
                    self._detected_tag_poses
                )

    def _update_fast(self) -> bool:
        """Process results using the ctypes fast reader. Returns True if any results."""
        had_results = False

        for cam in self.cameras:
            connected = cam.fast_sub.is_connected()
            if not connected:
                # Temp debug: log connection status
                self._nt_vision.putString(
                    f"debug/{cam.name}/status", "disconnected"
                )
                continue

            results = cam.fast_sub.read_queue()
            self._nt_vision.putNumber(
                f"debug/{cam.name}/result_count", len(results)
            )
            for result in results:
                had_results = True
                n_targets = len(result.targets)
                has_mt = result.multitag_result is not None
                self._nt_vision.putString(
                    f"debug/{cam.name}/last_result",
                    f"targets={n_targets} multitag={has_mt}"
                )
                try:
                    self._process_fast_result(cam, result)
                except Exception as e:
                    self._nt_vision.putString(
                        f"debug/{cam.name}/error", str(e)
                    )

        return had_results

    def _update_sim(self) -> bool:
        """Process results using photonlibpy (sim mode). Returns True if any results."""
        had_results = False

        for cam in self.cameras:
            # Skip isConnected() in sim — VisionSystemSim doesn't publish
            # heartbeats, so isConnected() always returns False.
            for result in cam.photon_camera.getAllUnreadResults():
                had_results = True
                self._process_photonlib_result(cam, result)

        return had_results

    # ── Fast-reader result processing ──────────────────────────────────

    def _process_fast_result(self, cam: VisionCamera, result) -> None:
        """Process a FastPhotonResult — try multi-tag, fall back to single-tag."""
        is_multi_tag = result.multitag_result is not None
        estimated_pose_3d: Optional[Pose3d] = None
        timestamp = result.timestamp_sec
        target_ids: List[int] = []

        if is_multi_tag:
            # Multi-tag: coprocessor-computed pose
            best_tf = result.multitag_result.bestTransform
            estimated_pose_3d = (
                Pose3d()
                .transformBy(best_tf)
                .relativeTo(self.field_layout.getOrigin())
                .transformBy(cam.robot_to_camera.inverse())
            )
            target_ids = result.multitag_result.fiducialIDsUsed
        elif result.targets:
            # Single-tag fallback: lowest ambiguity fiducial target
            best_target = None
            best_ambiguity = 10.0
            for t in result.targets:
                if (t.poseAmbiguity != -1
                        and t.poseAmbiguity < best_ambiguity):
                    best_ambiguity = t.poseAmbiguity
                    best_target = t

            if best_target is not None:
                tag_pose = self._tag_pose_cache.get(best_target.fiducialId)
                if tag_pose is not None:
                    estimated_pose_3d = (
                        tag_pose
                        .transformBy(
                            best_target.bestCameraToTarget.inverse()
                        )
                        .transformBy(cam.robot_to_camera.inverse())
                    )
                    target_ids = [best_target.fiducialId]

        if estimated_pose_3d is None:
            return

        # Collect tag IDs and poses for telemetry
        for tid in target_ids:
            self._detected_tag_ids.append(tid)
            cached = self._tag_pose_cache.get(tid)
            if cached is not None:
                self._detected_tag_poses.append(cached.toPose2d())

        self._apply_estimate(
            estimated_pose_3d, target_ids, timestamp, is_multi_tag,
            targets=result.targets,
        )

    # ── Photonlib (sim) result processing ──────────────────────────────

    def _process_photonlib_result(self, cam: VisionCamera, result) -> None:
        """Process a photonlibpy PhotonPipelineResult (sim mode)."""
        pose_est = cam.pose_estimator.estimateCoprocMultiTagPose(result)
        is_multi_tag = pose_est is not None

        if pose_est is None:
            pose_est = cam.pose_estimator.estimateLowestAmbiguityPose(result)

        if pose_est is None:
            return

        estimated_pose_3d: Pose3d = pose_est.estimatedPose
        targets_used = pose_est.targetsUsed
        timestamp = pose_est.timestampSeconds

        target_ids = [t.fiducialId for t in targets_used]
        for tid in target_ids:
            self._detected_tag_ids.append(tid)
            cached = self._tag_pose_cache.get(tid)
            if cached is not None:
                self._detected_tag_poses.append(cached.toPose2d())

        self._apply_estimate(
            estimated_pose_3d, target_ids, timestamp, is_multi_tag,
            targets=targets_used,
        )

    # ── Shared filtering + pose estimator feed ─────────────────────────

    def _apply_estimate(
        self,
        estimated_pose_3d: Pose3d,
        target_ids: List[int],
        timestamp: float,
        is_multi_tag: bool,
        targets=None,
    ) -> None:
        """Filter, compute std devs, and feed to the drivetrain pose estimator."""
        if not self._passes_filters(
            estimated_pose_3d, targets or [], is_multi_tag
        ):
            self._rejected_count += 1
            return

        std_devs = self._compute_std_devs(estimated_pose_3d, target_ids)

        if all(s == float('inf') for s in std_devs):
            self._rejected_count += 1
            return

        self._accepted_count += 1
        pose_2d = estimated_pose_3d.toPose2d()
        self.drivetrain.add_vision_pose_estimate(pose_2d, timestamp, std_devs)

        self._accepted_pose_pub.set(pose_2d)
        self._nt_vision.putNumberArray("last_std_devs", list(std_devs))

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
        target_ids: List[int],
    ) -> Tuple[float, float, float]:
        """Compute dynamic standard deviations based on tag count and distance."""
        num_tags = 0
        total_dist = 0.0

        # Hoist conversion out of the loop
        robot_translation = estimated_pose.toPose2d().translation()

        for tid in target_ids:
            tag_trans = self._tag_translation_cache.get(tid)
            if tag_trans is None:
                continue
            num_tags += 1
            total_dist += tag_trans.distance(robot_translation)

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

    # ── Simulation support ──────────────────────────────────────────────

    def setup_sim(self) -> None:
        """Create VisionSystemSim with a PhotonCameraSim per camera.

        Call once during sim init (from physics.py). Imports are deferred so
        cv2 and the simulation module are never loaded on real hardware.
        """
        from photonlibpy.simulation import (
            PhotonCameraSim,
            SimCameraProperties,
            VisionSystemSim,
        )

        self._vision_sim = VisionSystemSim("main")
        self._vision_sim.addAprilTags(self.field_layout)

        for vcam in self.cameras:
            props = SimCameraProperties.PERFECT_90DEG()
            cam_sim = PhotonCameraSim(vcam.photon_camera, props)
            self._vision_sim.addCamera(cam_sim, vcam.robot_to_camera)

    def update_sim(self, robot_pose) -> None:
        """Feed ground-truth pose into VisionSystemSim.

        Call each physics tick from physics.py so cameras see simulated
        AprilTag detections.
        """
        if hasattr(self, '_vision_sim'):
            self._vision_sim.update(robot_pose)
