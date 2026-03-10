# CAN Configuration Conventions

## CAN ID assignment

### Robot Nervous System

- The RoboRIO is assigned CAN ID 1.
- The radio is assigned CAN ID 2.
- Additional servers connected to CAN, such as a camera server, are assigned starting at CAN ID 3.

### Drivetrain

- The drivetrain motors and absolute encoders will be assigned starting at CAN ID 50.  
- A single drivetrain module will have consecutive CAN IDs and corresponding components will have corresponding IDs in each run of CAN IDs.
    - For Example: A 4-module swerve drivetrain uses 4x3=12 CAN IDs. These would be assigned as [[50, 51, 52], [53, 54, 55], [56, 57, 58], [59, 60, 61]], with each set of three representing drive motor, steer motor, and absolute angle encoder respectively.
- The most central module or set of modules on the chassis after the drivetrain will occupy CAN IDs counting up from 40, and modules will count backwards from there, such that the most distal module/mechanism occupies the lowest 2-digit CAN IDs.

### Mechanisms

Current mechanism CAN ID assignments (counting backwards from 40):

| Mechanism | CAN IDs | Notes |
|-----------|---------|-------|
| Intake    | 40 (deploy), 41 (roller) | Placeholder — update when hardware is wired |
| Turret    | 38 | Placeholder — update when hardware is wired |