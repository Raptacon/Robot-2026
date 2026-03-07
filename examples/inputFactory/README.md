# InputFactory Example

Demonstrates `utils.input.InputFactory` — config-driven controller input management replacing hardcoded `XboxController` calls.

Based on the [WPILib SwerveBot example](https://github.com/robotpy/examples/tree/main/SwerveBot) with additions showing InputFactory features.

## What This Shows

### Config-Driven Analog Axes
Instead of manually applying deadband, inversion, and scaling inline:
```python
# BEFORE (hardcoded):
xSpeed = -slewLimiter.calculate(
    wpimath.applyDeadband(controller.getLeftY(), 0.02)) * kMaxSpeed
```

All shaping comes from `controller_config.yaml`:
```python
# AFTER (InputFactory):
forward = factory.getAnalog("drivetrain.forward")
xSpeed = forward()  # deadband, invert, scale all from YAML
```

### Auto-Binding with `.bind()`
The trigger mode (`on_true`, `while_true`, `toggle_on_true`, etc.) is declared in YAML. The `.bind()` method selects the correct `commands2.Trigger` binding automatically:
```python
factory.getButton("led.while_held").bind(led.whileHeldCommand())
factory.getButton("led.toggle").bind(led.toggleCommand())
```

### Default Command with Subsystem-Owned Axes
The drivetrain is a `commands2.Subsystem` that accepts ManagedAnalog callables in its constructor. A default command (`RunCommand`) reads them each cycle — the robot class doesn't drive directly:
```python
swerve = Drivetrain(forward, strafe, rotate)
swerve.setDefaultCommand(swerve.defaultDriveCommand(fieldRelative=True))
```

### Toggle Button for Axis Swap
Press the back button to toggle between normal and swapped stick layouts. The swap lives inside the drivetrain subsystem — it swaps which stored callable provides forward vs rotate. The default command doesn't need to know about the swap:
```python
factory.getButton("drivetrain.swap_axes").bind(swerve.swapAxesCommand())
```

### LED Subsystem
Simple DIO-based LED with two bindings:
- **A button** — LED on while held (`while_true`)
- **B button** — toggle LED on/off each press (`on_true`)

### Rumble Feedback
A brief rumble pulse on teleop start using `ManagedRumble.set(value, timeout)`.

## Files

| File | Description |
|------|-------------|
| `robot.py` | Main robot — uses InputFactory for all controls |
| `controller_config.yaml` | YAML config defining actions and bindings |
| `drivetrain.py` | Swerve drivetrain subsystem with default command and axis swap |
| `swervemodule.py` | Swerve module (from WPILib example) |
| `led.py` | Simple LED subsystem with command factories |
| `controller_map.png` | Exported controller binding map (landscape) |

## Running

```bash
cd examples/inputFactory
python -m robotpy sim
```

## Editing Bindings

Open the config in the GUI tool to visually reassign buttons and axes:
```bash
python -m host.controller_config examples/inputFactory/controller_config.yaml
```

## Generating the Controller Map Image

Export the current bindings to a PNG for documentation or quick reference:
```bash
python -m host.controller_config examples/inputFactory/controller_config.yaml \
    --export examples/inputFactory/controller_map.png --orientation landscape
```

Supported options:
- `--export <path>` — output file (`.png` or `.pdf`)
- `--orientation landscape|portrait` — page orientation (default: portrait)
