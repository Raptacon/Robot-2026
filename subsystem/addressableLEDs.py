import wpilib
import math
from constants.swerve_constants import LEDConstants

class AddressableLEDs:
    def __init__(self):        
        self.led = wpilib.AddressableLED(LEDConstants.LEDPort)
        self.led.setLength(LEDConstants.LEDLength)
        self.ledBuffer = []
        self.ledData = wpilib.AddressableLED.LEDData()
    
        self.sonarPosition = 0
        self.sonarVelocity = 0.25
    def LEDConstantColor(self, color) -> None:
        for i in range(LEDConstants.LEDLength):
            self.ledData.setLED(color)
            self.ledBuffer.append(self.ledData)
        self.led.setData(self.ledBuffer)
        self.led.start()
        
    def LEDSonarPeriodic(self, color) -> None:
        for i in range(LEDConstants.LEDLength):
            if math.floor(self.sonarPosition) == i:
                self.ledData.setLED(color)
            else:
                self.ledData.setLED(wpilib.Color.kBlack)
        self.led.setData(self.ledBuffer)
        self.led.start()
        
        self.sonarPosition += self.sonarVelocity
        if math.floor(self.sonarPosition) <= LEDConstants.LEDLength:
            self.sonarVelocity *= -1
        elif math.floor(self.sonarPosition) >= 0:
            self.sonarVelocity *= -1