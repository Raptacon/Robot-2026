"""Match monitor entry point. Usage: python -m host.match_monitor [--port 8510] [--output-dir ...]"""

import argparse
from .receiver import run_server


def main():
    parser = argparse.ArgumentParser(description='FRC Robot Match Monitor - Log Receiver')
    parser.add_argument('--port', type=int, default=5800,
                        help='Port to listen on (default: 5800)')
    parser.add_argument('--output-dir', type=str, default=None,
                        help=r'Directory to save received logs (default: C:\Users\Public\Documents\FRC\Log Files\WPILogs)')
    parser.add_argument('--bind', type=str, default='0.0.0.0',
                        help='Address to bind to (default: 0.0.0.0)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug logging (shows connection attempts)')
    parser.add_argument('--tray', action='store_true',
                        help='Run as a Windows system tray application (requires pystray)')
    args = parser.parse_args()

    if args.tray:
        # If launched from python.exe (has a console window), re-launch under
        # pythonw.exe so the originating shell/cmd window closes immediately.
        import ctypes, sys, subprocess
        from pathlib import Path
        if ctypes.windll.kernel32.GetConsoleWindow():
            pythonw = Path(sys.executable).with_name('pythonw.exe')
            if pythonw.exists():
                # sys.argv[0] is the __main__.py path when using -m, so
                # reconstruct the command with explicit -m to preserve imports.
                subprocess.Popen(
                    [str(pythonw), '-m', 'host.match_monitor'] + sys.argv[1:],
                )
                sys.exit(0)
        from .tray_app import run_server_tray
        run_server_tray(args.bind, args.port, args.output_dir, debug=args.debug)
    else:
        run_server(args.bind, args.port, args.output_dir, debug=args.debug)


if __name__ == '__main__':
    main()
