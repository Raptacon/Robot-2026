import json
import os
from pathlib import Path

import wpilib


def get_deploy_info(key: str) -> str:
    """Read a value from ~/py/deploy.json.

    Args:
        key: JSON key to retrieve (e.g. "git-hash", "deploy-host", "deploy-user", "git-branch")

    Returns:
        The value for the key, or a fallback string if the file is missing or malformed.
    """
    deploy_file = os.path.join(str(Path.home()), "py", "deploy.json")
    try:
        with open(deploy_file, "r") as f:
            data = json.load(f)
            return data.get(key, f"Key: {key} Not Found in JSON")
    except OSError:
        return "unknown"
    except json.JSONDecodeError:
        return "bad json in deploy file check for unescaped "


def publish_deploy_info() -> None:
    """Publish deploy metadata to SmartDashboard."""
    wpilib.SmartDashboard.putString("Robot Version", get_deploy_info("git-hash"))
    wpilib.SmartDashboard.putString("Git Branch", get_deploy_info("git-branch"))
    wpilib.SmartDashboard.putString("Deploy Host", get_deploy_info("deploy-host"))
    wpilib.SmartDashboard.putString("Deploy User", get_deploy_info("deploy-user"))
