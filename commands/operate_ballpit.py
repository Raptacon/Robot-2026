import commands2
from subsystem.ballpit import BallPitHopper

class OperateBallPit(commands2.Command):
    def __init__(self, hopper: BallPitHopper, isStuck: bool) -> None:
        """
        Adds requirements & initializes class OperateBallPit

        Args: 
            hopper: the Hopper Subsystem that this command will operate
            isStuck: True if game pieces are stuck in the hopper

        Returns: 
            None - class initialization executed upon construction
        
        """
        super().__init__()
        self.hopper = hopper
        self.isStuck = isStuck

        self.addRequirements(self.hopper)

    def execute(self):
        """
        Runs the Hex Shaft in the Hopper based on if there is a game piece stuck or not.
        
        Returns:
            None - this is just executing operations
        """
        if(self.isStuck):
            self.hopper.runHexShaft(-0.75)
        else:
            self.hopper.runHexShaft(0.5)
