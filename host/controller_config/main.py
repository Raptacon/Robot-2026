"""Entry point for the controller configuration GUI tool.

Usage:
    python -m host.controller_config [config.yaml]
    python host/controller_config/main.py [config.yaml]

CLI export (no GUI):
    python -m host.controller_config config.yaml --export out.png
    python -m host.controller_config config.yaml --export out.pdf --orientation landscape
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is importable
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


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
    parser.add_argument(
        "--export", metavar="OUTPUT",
        help="Export controller layout to PNG or PDF (no GUI)",
    )
    parser.add_argument(
        "--orientation", choices=["portrait", "landscape"],
        default="portrait",
        help="Page orientation for export (default: portrait)",
    )
    parser.add_argument(
        "--hide-unassigned", action="store_true",
        help="Hide inputs with no bindings in export",
    )
    args = parser.parse_args()

    if args.export:
        # CLI export mode — no GUI
        if not args.config_file:
            parser.error("config_file is required when using --export")

        from utils.controller.config_io import load_config
        from host.controller_config.app import load_settings
        from host.controller_config.print_render import export_pages

        config_path = Path(args.config_file)
        if not config_path.exists():
            print(f"Error: config file not found: {config_path}",
                  file=sys.stderr)
            sys.exit(1)

        config = load_config(config_path)
        settings = load_settings()
        label_positions = settings.get("label_positions", {})

        output_path = Path(args.export)
        try:
            export_pages(config, args.orientation, output_path,
                         label_positions, args.hide_unassigned)
            print(f"Exported to {output_path}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # GUI mode
        from host.controller_config.app import ControllerConfigApp
        app = ControllerConfigApp(initial_file=args.config_file)
        app.mainloop()


if __name__ == "__main__":
    main()
