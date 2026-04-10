# Native imports
import math
from typing import Callable

# Internal imports
from constants import SwerveDriveConsts
from subsystem.drivetrain.swerve_drivetrain import SwerveDrivetrain

# Third-party imports
import commands2


def circle_to_square(x: float, y: float) -> tuple[float, float]:
    """
    Map joystick input from a circular domain to a square [-1,1] x [-1,1] domain.

    Xbox joystick hardware constrains the stick to a circle, so diagonal inputs
    max out at ~0.707 per axis. This remaps so that any direction at full
    deflection produces full output on both axes.

    Method: at angle theta, the unit circle edge is at radius 1 while the unit
    square edge is at radius 1/max(|cos(theta)|, |sin(theta)|). We scale the
    input vector by the ratio (square_edge / circle_edge) so the circle maps
    onto the square. Partial deflection is preserved proportionally.

    For background on disc-to-square mappings see:
    https://arxiv.org/abs/1509.06344 (Fong, "Analytical Methods for Squaring the Disc")
    https://en.wikipedia.org/wiki/Squircle

    Args:
        x: joystick X input, expected within [-1, 1] (circular constraint)
        y: joystick Y input, expected within [-1, 1] (circular constraint)

    Returns:
        (sx, sy) remapped to fill the square [-1, 1] x [-1, 1]
    """
    ax = abs(x)
    ay = abs(y)
    max_component = max(ax, ay)

    if max_component < 1e-6:
        return (0.0, 0.0)

    # At this angle, the unit circle is at radius 1 and the unit square
    # edge is at radius r/max(|x|,|y|) where r = hypot(x,y).
    # Scale = square_edge_r / circle_r = (r / max_component) / 1
    # But we want each component scaled so full circle deflection -> square edge.
    # Simplification: scale = hypot(x,y) / max_component
    r = math.hypot(x, y)
    scale = r / max_component

    sx = x * scale
    sy = y * scale

    return (max(-1.0, min(1.0, sx)), max(-1.0, min(1.0, sy)))


class DefaultDriveCircular(commands2.Command):
    """
    Default swerve drive command that remaps circular joystick input to a
    square output space. This ensures diagonal inputs produce full translation
    speed, not the ~70% that raw circular inputs give.
    """
    def __init__(
        self,
        drivetrain: SwerveDrivetrain,
        velocity_vector_x: Callable[[], float],
        velocity_vector_y: Callable[[], float],
        angular_velocity: Callable[[], float],
        field: Callable[[], bool]
    ) -> None:
        """
        Args:
            drivetrain: the swerve drivetrain subsystem
            velocity_vector_x: X translation input [-1, 1] (circular)
            velocity_vector_y: Y translation input [-1, 1] (circular)
            angular_velocity: rotation input [-1, 1]
            field: if True, field-relative; if False, robot-relative
        """
        super().__init__()

        self.drivetrain = drivetrain
        self.velocity_vector_x = velocity_vector_x
        self.velocity_vector_y = velocity_vector_y
        self.angular_velocity = angular_velocity
        self.field = field
        self.addRequirements(self.drivetrain)

    def execute(self) -> None:
        raw_x = self.velocity_vector_x()
        raw_y = self.velocity_vector_y()

        # Remap circular stick input to fill the square output space
        sq_x, sq_y = circle_to_square(raw_x, raw_y)

        self.drivetrain.drive(
            sq_x * SwerveDriveConsts.maxTranslationMPS,
            sq_y * SwerveDriveConsts.maxTranslationMPS,
            self.angular_velocity() * math.radians(SwerveDriveConsts.maxAngularDPS),
            self.field()
        )
