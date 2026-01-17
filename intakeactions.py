import wpilib
import commands2
import rev

intakeVelocity = 0.3; #Speed in which the intake motor will move upon deployment/stowing
intakeMotorThreshold = 1; #Used to determine whether or not intake is deployed
rollerVelocity = 0.3; #Speed in which the roller motor will move upon deployment

class IntakeSubsystem(commands2.SubsystemBase):
    def __init__(self):
        #Initialize Intake
        self.intakeMotor = rev.SparkMax(1, rev.SparkLowLevel.MotorType.kBrushless)
        self.intakeMotorEncoder = self.intakeMotor.getEncoder()
        self.intakeMotorPosition = self.intakeMotorEncoder.getPosition()

        #Initialize Roller
        self.rollerMotor = rev.SparkMax(2, rev.SparkLowLevel.MotorType.kBrushless)
        self.rollerMotorEncoder = self.RollerMotor.getEncoder()
        self.rollerMotorVelocity = self.intakeRollerEncoder.getVelocity()

    #Deploy the intake  
    def deployIntake(self):
        
        ###Check Sensor for deployment, if not, deploy it.
        if self.intakeMotorPosition == 0:

            #Runs until Sensor returns deployment complete
            while True:

                ###Apply voltage to motor for deployment
                self.intakeMotor.set(intakeVelocity);
                
                ###Stop voltage to motor
                self.intakeMotor.set(0);

                ###Check Sensor for deployment complete
                if self.intakeMotorPosition >= intakeMotorThreshold:
                    break

                #####If not fully deployed, start voltage for deployment, then stop voltage

    #Activate Roller
    def activateRoller(self):

        ###Apply voltage to roller until it starts moving
        while self.rollerMotorVelocity == 0:

            ###Apply voltage to activate roller
            self.rollerMotor.set(rollerVelocity);
        
            ###Check Sensor
            
            pass #Gets rid of indentation error

    #Stow the Intake; more or less the opposite of the deployIntake function
    def stowIntake(self):
        ###Check Sensor for deployment, if it is, stow it.
        if self.intakeMotorPosition != 0:

            #Runs until Sensor returns stow complete
            while True:

                ###Apply opposite voltage than used for deployment to motor
                self.intakeMotor.set(-intakeVelocity);
                
                ###Stop voltage to motor
                self.intakeMotor.set(0);

                ###Check Sensor for deployment complete
                if self.intakeMotorPosition == 0:
                    break

                #####If not fully deployed, start voltage for deployment, then stop voltage