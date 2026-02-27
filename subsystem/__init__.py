# Importing each subsystem module triggers its register_subsystem() call.
# To add a new subsystem, add one import line here.
import subsystem.drivetrain.swerve_drivetrain   # registers "drivetrain"
import subsystem.mechanisms.turret              # registers "turret"
