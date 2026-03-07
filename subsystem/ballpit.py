import commands2
import rev

class BallPitHopper(commands2.Subsystem):
    def __init__(self) -> None:
        """
        Creates the hopper motor
        
        Returns:
            None - class initialization executed upon construction
        """
        self.hopperMotor = rev.SparkMax(21, rev.SparkLowLevel.MotorType.kBrushless)

    def runHexShaft(self, percent : float):
        """
        Sets the motor percentage for use elsewhere
        
        Args: 
            percent: speed of the hopper motor from -1.0 - 1.0

        Returns: 
            None - function to be used elsewhere
        """
        self.hopperMotor.set(percent)

    def unjamHopper(self):
        return commands2.cmd.sequence(
        commands2.cmd.run(lambda: self.hopperMotor.set(-0.5), self).withTimeout(0.5),
        commands2.cmd.run(lambda: self.hopperMotor.set(0.5), self).withTimeout(0.5)
        )