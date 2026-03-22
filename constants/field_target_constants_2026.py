from wpimath.geometry import Translation2d


class FieldTargets2026:
    """
    Define targets on the field that a shooter could aim for.
    Coordinates are given in (x, y) translations relative to the origin
    on an always-bue coordinate system (observing the field top-down with)
    the blue alliance on the left, the bottom-left corner is (0, 0)).
    X represents the horizontal axis and Y represents the vertical axis.
    """
    blueHubTarget = Translation2d(4.625594, 4.034536)
    redHubTarget = Translation2d(11.915394, 4.034536)
    bottomLeftTarget = Translation2d(1, 1)
    bottomRightTarget = Translation2d(15.540988, 1)
    topLeftTarget = Translation2d(1, 7.069326)
    topRightTarget = Translation2d(15.540988, 7.069326)
