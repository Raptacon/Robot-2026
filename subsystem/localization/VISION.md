# Vision Pose Estimation with PhotonVision AprilTags

Best practices and implementation guide for fusing PhotonVision AprilTag data
with WPILib's `SwerveDrive4PoseEstimator`.

## How the Pipeline Works

1. **PhotonVision** (coprocessor) detects AprilTags, identifies corners, decodes tag IDs.
2. **Single-tag SolvePnP** produces two possible camera-to-tag transforms (inherently
   ambiguous -- the same 2D corners can map to two 3D poses).
3. **Multi-tag estimation** combines all visible tag corners with the known field layout
   to compute a single unambiguous field-to-camera transform. Always preferred.
4. **`PhotonPoseEstimator`** converts camera-relative poses to field-relative robot
   poses using the known robot-to-camera `Transform3d`.
5. **`SwerveDrive4PoseEstimator.addVisionMeasurement()`** fuses the vision pose with
   wheel odometry via a simplified Kalman filter with latency compensation.

## Key photonlibpy API

```python
from photonlibpy import PhotonCamera, PhotonPoseEstimator
from robotpy_apriltag import AprilTagField, AprilTagFieldLayout
from wpimath.geometry import Transform3d, Translation3d, Rotation3d

cam = PhotonCamera("camera_name")

estimator = PhotonPoseEstimator(
    AprilTagFieldLayout.loadField(AprilTagField.kDefaultField),
    Transform3d(
        Translation3d(x_m, y_m, z_m),       # robot center -> camera
        Rotation3d.fromDegrees(roll, pitch, yaw),
    ),
)
```

### Estimation methods (all return `Optional[EstimatedRobotPose]`)

| Method | When to use |
|--------|-------------|
| `estimateCoprocMultiTagPose(result)` | First choice. Most accurate, no ambiguity. |
| `estimateLowestAmbiguityPose(result)` | Fallback when only one tag visible. |

### Reading results

Use `getAllUnreadResults()` **not** `getLatestResult()`. The camera publishes into
a FIFO queue (depth 20). `getLatestResult()` can miss or duplicate frames.

```python
for result in camera.getAllUnreadResults():
    # process each PhotonPipelineResult
```

## Kalman Filter Weighting

WPILib's pose estimator uses a simplified Kalman filter. The gain for each axis
(x, y, theta) is computed independently:

```
K = Q / (Q + sqrt(Q * R))
```

- **Q** = state (odometry) std dev squared -- default `(0.1, 0.1, 0.1)`.
- **R** = vision std dev squared -- default `(0.9, 0.9, 0.9)`.
- With defaults: K ~ 0.1, so only ~10% of each vision correction is applied.
- **Smaller std dev = more trust.**
- Setting std dev to `float('inf')` = ignore that axis entirely.

Vision measurements are **latency-compensated**: the estimator interpolates back
through a 1.5-second buffer to the camera frame's timestamp, applies the scaled
correction, then replays odometry forward to the present.

## Filtering Bad Data

Apply these filters **before** calling `addVisionMeasurement()`:

| Filter | Threshold | Rationale |
|--------|-----------|-----------|
| **Ambiguity** (single-tag) | > 0.2 reject | Two PnP solutions too similar to disambiguate |
| **Distance** (single-tag) | > 4 m reject | Accuracy degrades rapidly at range |
| **Field bounds** | Outside field + 0.5 m margin | Physically impossible pose |
| **Z-height** | abs(z) > 0.5 m | Robot should be on the carpet |
| **Rotation vs gyro** | > 20 deg difference | Catches "flipped pose" from bad PnP |

### Ambiguity explained

`poseAmbiguity` is the ratio of reprojection errors between the two PnP solutions:
- **0.0** = one solution is clearly correct (multi-tag always reports 0).
- **> 0.2** = both solutions are plausible; the pose is unreliable.
- **1.0** = coin flip. Reject.

High ambiguity happens when viewing a tag head-on (perpendicular). Mount cameras
at oblique angles to avoid this.

## Dynamic Standard Deviations

The consensus approach from YAGSL, HuskieRobotics (3061), FRC 5712, and WPILib docs:

```python
SINGLE_TAG_STD_DEVS = (4.0, 4.0, float('inf'))
MULTI_TAG_STD_DEVS  = (0.5, 0.5, 1.0)

def get_std_devs(estimated_pose, targets_used, field_layout):
    num_tags = 0
    avg_dist = 0.0
    for target in targets_used:
        tag_pose = field_layout.getTagPose(target.fiducialId)
        if tag_pose is None:
            continue
        num_tags += 1
        avg_dist += tag_pose.toPose2d().translation().distance(
            estimated_pose.toPose2d().translation()
        )
    if num_tags == 0:
        return SINGLE_TAG_STD_DEVS
    avg_dist /= num_tags

    base = MULTI_TAG_STD_DEVS if num_tags > 1 else SINGLE_TAG_STD_DEVS

    if num_tags == 1 and avg_dist > 4.0:
        return (float('inf'), float('inf'), float('inf'))

    scale = 1.0 + (avg_dist ** 2 / 30.0)
    return tuple(s * scale for s in base)
```

### Key principles

- **Never trust single-tag rotation** -- set theta std dev to `inf`; rely on gyro.
- **Multi-tag is dramatically better** -- tighter base std devs (0.5 m vs 4.0 m).
- **Scale quadratically with distance** -- error grows with distance squared.
- **Reject single-tag > 4 m entirely** -- too inaccurate to be useful.

### Approximate Kalman gain at various settings

| Vision std dev | Kalman gain K | Meaning |
|---------------|---------------|---------|
| 0.1 (= state) | 0.50 | Equal trust vision and odometry |
| 0.5 | 0.17 | Moderate vision trust |
| 0.9 (default) | 0.10 | Low vision trust (WPILib default) |
| 4.0 | 0.02 | Very low trust (single-tag base) |
| inf | 0.00 | Vision ignored |

## Common Pitfalls

1. **Head-on viewing angle** -- PnP solver fails when camera is perpendicular to
   tag face. Mount cameras at oblique angles.
2. **Camera calibration** -- The #1 source of systematic error. Calibrate carefully
   through the PhotonVision web UI with many images at various angles and distances.
3. **Coordinate system mismatch** -- Use "always blue" origin everywhere. PhotonVision
   field layouts use blue-alliance origin by convention.
4. **Stale timestamps after code restart** -- PhotonVision can report old timestamps.
   Validate that timestamps are not in the future.
5. **USB port ordering** -- Camera names can swap if USB ports change. Always plug
   cameras into the same physical port on the coprocessor.
6. **Only processing in teleop** -- Vision should run in `periodic()` (all modes),
   not just `teleopPeriodic()`. Autonomous needs vision correction too.
7. **Not draining the result queue** -- Process ALL results from
   `getAllUnreadResults()`, not just the last one. Each has a unique timestamp for
   proper latency compensation.

## Architecture in This Codebase

The `Localization` subsystem owns camera connections and pose estimation logic.
It calls `drivetrain.add_vision_pose_estimate(pose2d, timestamp, std_devs)` which
is a thin wrapper around `SwerveDrive4PoseEstimator.addVisionMeasurement()`.

The drivetrain owns the fused pose. Other subsystems (shooter, turret, auto) should
read `drivetrain.current_pose()` for the best available position, not raw vision data.

## Simulation

The vision system is fully simulated when running `python -m robotpy sim`.

### How it works

1. `Localization.setup_sim()` creates a `VisionSystemSim` with `PhotonCameraSim`
   wrappers around each real `PhotonCamera`.
2. `physics.py` calls `localization.update_sim(ground_truth_pose)` each tick.
3. `VisionSystemSim` ray-traces the field's AprilTag layout to determine which
   tags each camera can see, then publishes simulated `PhotonPipelineResult`
   data through NetworkTables.
4. The normal `Localization.update()` in `robotPeriodic()` reads these results
   as if they came from real cameras -- the entire filtering, std dev, and pose
   estimator pipeline runs identically in sim and on hardware.

### Running the sim

```bash
python -m robotpy sim
```

### Camera properties

By default, `SimCameraProperties.PERFECT_90DEG()` is used (no noise, no
latency, 90-degree FOV). To test with realistic noise, modify `setup_sim()`:

```python
props = SimCameraProperties.PERFECT_90DEG()
props.setCalibError(0.25, 0.05)   # avg/stddev pixel noise
props.setAvgLatency(0.035)         # 35ms average latency
props.setLatencyStdDev(0.008)      # 8ms jitter
props.setFPS(30)                   # 30 fps
```

### Physics model

The current zero-delay swerve model is sufficient for vision testing. The
vision pipeline depends on accurate *position* (which tags are visible), not
on realistic motor dynamics. A physics model upgrade (DCMotorSim, low-pass
filter) would improve auto path / PID tuning fidelity but is independent of
vision correctness.

## Visualization with AdvantageScope

[AdvantageScope](https://docs.advantagescope.org/) is the primary visualization
tool for debugging vision in sim. It connects to the robot sim via
NetworkTables on localhost.

### Setup

1. Open AdvantageScope (bundled with WPILib)
2. Connect to `localhost` (File > Connect to Simulator)
3. Open the **3D Field** tab

### What you can see

- **Ground-truth pose** (from physics.py `Field2d`) -- the "real" robot position
- **Estimated pose** (from `drivetrain.current_pose()`) -- the fused odometry +
  vision estimate
- **Vision target detections** -- drag poses from the `VisionSystemSim-main/`
  NT subtree onto the field
- **Camera poses** -- auto-published by `VisionSystemSim`

The 3D field tab includes the 2026 field model with AprilTag positions already
built in. You can overlay estimated vs actual pose as solid + ghost robot models
to visualize how well vision is correcting odometry drift.

### Custom robot models

Export your robot CAD as `.glb` (binary glTF) and load it in AdvantageScope
preferences under custom assets. See the
[AdvantageScope docs](https://docs.advantagescope.org/more-features/custom-assets/).

## References

### PhotonVision Documentation

- [PhotonVision Pose Estimation Docs](https://docs.photonvision.org/en/latest/docs/programming/photonlib/robot-pose-estimator.html) -- `PhotonPoseEstimator` API, estimation strategies, usage examples
- [PhotonVision Multi-Tag Pipeline](https://docs.photonvision.org/en/latest/docs/apriltag-pipelines/multitag.html) -- How multi-tag estimation works on the coprocessor, how to enable it
- [PhotonVision 3D Tracking / Ambiguity](https://docs.photonvision.org/en/latest/docs/apriltag-pipelines/3D-tracking.html) -- SolvePnP ambiguity explained, why head-on viewing fails
- [PhotonVision Advanced Strategies](https://docs.photonvision.org/en/latest/docs/integration/advancedStrategies.html) -- Field layout loading, coordinate systems, latency compensation
- [PhotonVision Pose Estimation Example (Python)](https://github.com/PhotonVision/photonvision/blob/main/photonlib-python-examples/poseest/robot.py) -- Official Python example showing full integration
- [PhotonPoseEstimator Source (Python)](https://github.com/PhotonVision/photonvision/blob/main/photon-lib/py/photonlibpy/photonPoseEstimator.py) -- Source code for the Python pose estimator
- [PhotonVision Camera Calibration](https://docs.photonvision.org/en/latest/docs/calibration/calibration.html) -- How to calibrate cameras (critical for accuracy)

### WPILib Documentation

- [WPILib Pose Estimators](https://docs.wpilib.org/en/stable/docs/software/advanced-controls/state-space/state-space-pose-estimators.html) -- How `SwerveDrivePoseEstimator` works, Kalman filter math, std dev tuning
- [WPILib AprilTag Intro](https://docs.wpilib.org/en/stable/docs/software/vision-processing/apriltag/apriltag-intro.html) -- How AprilTag detection works, 2D-to-3D ambiguity, tunable parameters
- [WPILib Vision Processing](https://docs.wpilib.org/en/stable/docs/software/vision-processing/index.html) -- Overview of vision processing options in FRC
- [WPILib Coordinate Systems](https://docs.wpilib.org/en/stable/docs/software/basic-programming/coordinate-system.html) -- Robot and field coordinate conventions (X forward, Y left, Z up)
- [SwerveDrive4PoseEstimator RobotPy API](https://robotpy.readthedocs.io/projects/robotpy/en/stable/wpimath.estimator/SwerveDrive4PoseEstimator.html) -- Python-specific API reference
- [PoseEstimator.java Source](https://github.com/wpilibsuite/allwpilib/blob/main/wpimath/src/main/java/edu/wpi/first/math/estimator/PoseEstimator.java) -- WPILib source showing Kalman gain formula and latency compensation internals

### FRC Team Implementations

- [YAGSL Vision.java](https://github.com/BroncBotz3481/YAGSL-Example/blob/main/src/main/java/frc/robot/subsystems/swervedrive/Vision.java) -- Widely-used swerve library with distance-based std dev scaling, ambiguity filtering, and sanity checks. Our std dev formula is adapted from this.
- [HuskieRobotics 3061-lib (Team 3061)](https://github.com/HuskieRobotics/3061-lib) -- Comprehensive vision subsystem with per-camera std dev factors, reprojection error filtering, and gyro rotation agreement checks
- [Team 254 FRC-2024-Public](https://github.com/Team254/FRC-2024-Public) -- Cheesy Poofs' 2024 robot code; reference-quality vision integration
- [Team 6328 Mechanical Advantage](https://www.littletonrobotics.org/software-update-2-one-vision-ring-to-rule-them-all/) -- Blog post on their vision architecture, AdvantageKit logging approach, and pose estimation strategy
- [FRC 5712 Vision Implementation Workshop](https://www.frc5712.com/vision-implementation) -- Step-by-step tutorial with std dev formula: `xy = 0.5 * dist^2 / tag_count`

### Chief Delphi Discussions

- [Use PhotonVision to improve pose estimation via AprilTags](https://www.chiefdelphi.com/t/use-photovision-to-improve-pose-estimation-via-april-tags/511031) -- Community recommendations; points to YAGSL and 3061-lib as gold standard implementations
- [Pose estimation degrades when camera is normal to AprilTag plane](https://www.chiefdelphi.com/t/pose-estimation-degrades-when-the-camera-is-normal-to-the-apriltag-plane/514907) -- Explains why head-on viewing causes ambiguity; camera mounting angle advice
- [How to improve accuracy of swerve odometry pose estimation](https://www.chiefdelphi.com/t/how-to-improve-accuracy-of-swerve-odometry-pose-estimation/506754) -- Teams report 4-5 inch offset errors; discussion of tuning approaches
- [Difficulty with Robot Pose Estimation](https://www.chiefdelphi.com/t/difficulty-with-robot-pose-estimation-in-frc/506639) -- When to trust vision vs odometry, handling periods with no visible targets
- [MT2 Discrepancy with PoseEstimation (flipped across tag)](https://www.chiefdelphi.com/t/mt2-discrepancy-with-poseestimation-flipped-across-the-apriltag/507224) -- Gyro/coordinate system mismatch causing flipped poses; reinforces need for rotation agreement filter
