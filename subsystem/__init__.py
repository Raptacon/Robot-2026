# Importing each subsystem module triggers its register_subsystem() call.
# To add a new subsystem, add one import line here.
import subsystem.drivetrain.swerve2026Chassis   # registers swerve_module_* (4 entries)
import subsystem.drivetrain.swerve_drivetrain   # registers "drivetrain" (depends on modules)
import subsystem.intakeactions                   # noqa: F401 registers "intake"
import subsystem.mechanisms.turret              # noqa: F401 registers "turret"
