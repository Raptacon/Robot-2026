import commands2
import rev

class BallPitHopper(commands2.Subsystem):
    def __init__(self) -> None:
        """
        Creates the hopper motor
        
        Returns:
            None - class initialization executed upon construction
        """
        self.hopperMotor = rev.SparkMax(40, rev.SparkLowLevel.MotorType.kBrushless)
        self.lastSpeed = 0

    def setHexShaftSpeed(self, percent : float):
        """
        Sets the motor percentage for use elsewhere
        
        Args: 
            percent: speed of the hopper motor from -1.0 - 1.0

        Returns: 
            None - function to be used elsewhere
        """
        self.lastSpeed = percent

    def unjamHopper(self, percent, duration = 0.5, repeat = 1):
        self.pre_unjamSpeed = self.lastSpeed
        return commands2.cmd.sequence(
            commands2.cmd.repeatingSequence(
                commands2.cmd.runOnce(lambda: self.setHexShaftSpeed(-percent), self),
                commands2.cmd.waitSeconds(duration),
                commands2.cmd.runOnce(lambda: self.setHexShaftSpeed(percent), self),
                commands2.cmd.waitSeconds(duration)
            ).withTimeout(repeat * (duration * 2)),
            commands2.cmd.runOnce(lambda: self.setHexShaftSpeed(self.pre_unjamSpeed), self)
        )
    
    def hex_shaft_generator(self, percent):
        return commands2.cmd.runOnce(lambda: self.setHexShaftSpeed(percent), self)
    
    def periodic(self):
        commands2.cmd.print_(self.lastSpeed)