"""
2026 competition chassis configuration.

Registers 4 swerve modules with positions, CAN channels, inversions,
and encoder calibrations specific to the 2026 competition robot.
"""
from config import OperatorRobotConfig
from constants import SwerveDriveConsts, SwerveModuleName
from utils.subsystem_factory import SubsystemState, register_subsystem
from .swerve_module import SwerveModuleMk4iSparkMaxNeoCanCoder

_consts = SwerveDriveConsts()

_MODULE_CONFIGS = [
    (name, idx)
    for idx, name in enumerate(SwerveModuleName)
]


def _make_module_creator(name, idx):
    def creator(subs):
        return SwerveModuleMk4iSparkMaxNeoCanCoder(
            name=name,
            drivetrain_location=_consts.moduleLocations[name],
            channel_base=OperatorRobotConfig.swerve_module_channels[idx],
            invert_drive=_consts.moduleInvertDrive[name],
            invert_steer=_consts.moduleInvertSteer[name],
            encoder_calibration=OperatorRobotConfig.swerve_abs_encoder_calibrations[idx],
        )
    return creator


MODULE_NAMES = [f"swerve_module_{name}" for name, _ in _MODULE_CONFIGS]

for _name, _idx in _MODULE_CONFIGS:
    register_subsystem(
        name=f"swerve_module_{_name}",
        default_state=SubsystemState.enabled,
        creator=_make_module_creator(_name, _idx),
    )
