import commands2
import rev

class BallPitHopper(commands2.SubsystemBase):
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
