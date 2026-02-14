import commands2
from subsystem.ballpit import BallPitHopper

class OperateBallPit(commands2.Command):
    def __init__(self, hopper: BallPitHopper, isStuck: bool) -> None:
        super().__init__()
        self.hopper = hopper
        self.isStuck = isStuck

        self.addRequirements(self.hopper)

    def execute(self):
        if(self.isStuck):
            self.hopper.runHexShaft(-0.75)
        else:
            self.hopper.runHexShaft(0.5)
