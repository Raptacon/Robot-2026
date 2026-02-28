"""Entry point for the controller configuration GUI tool.

Usage:
    python -m host.controller_config [config.yaml]
    python host/controller_config/main.py [config.yaml]
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is importable
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from host.controller_config.app import ControllerConfigApp


def main():
    parser = argparse.ArgumentParser(
        description="FRC Controller Configuration Tool",
    )
    parser.add_argument(
        "config_file",
        nargs="?",
        default=None,
        help="Path to a YAML config file to open on launch",
    )
    args = parser.parse_args()

    app = ControllerConfigApp(initial_file=args.config_file)
    app.mainloop()


if __name__ == "__main__":
    main()
