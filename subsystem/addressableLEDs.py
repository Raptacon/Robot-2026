import wpilib
from constants.swerve_constants import LEDConstants

class AddressableLEDs:
    def __init__(self):        
        self.led = wpilib.AddressableLED(LEDConstants.LEDPort)
        self.led.setLength(LEDConstants.LEDLength)
        self.ledBuffer = []
        self.ledData = wpilib.AddressableLED.LEDData()
    
        self.sonarOffset = 0
        self.sonarSpeed = 1
    def LEDConstantColor(self, color) -> None:
        for i in range(LEDConstants.LEDLength):
            self.ledData.setLED(color)
            self.ledBuffer.append(self.ledData)
        self.led.setData(self.ledBuffer)
        self.led.start()
        
    def LEDBlipPeriodic(self, color) -> None:
        for i in range(LEDConstants.LEDLength):
            if (i + self.sonarOffset) % self.sonarSpeed == 0:
                self.ledData.setLED(color)
            else:
                self.ledData.setLED(wpilib.Color.kBlack)
        self.led.setData(self.ledBuffer)
        self.led.start()
        
        self.sonarOffset += self.sonarSpeed
        if self.sonarOffset == self.sonarSpeed:
            self.sonarOffset = 0