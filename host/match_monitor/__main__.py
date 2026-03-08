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
    args = parser.parse_args()
    run_server(args.bind, args.port, args.output_dir, debug=args.debug)


if __name__ == '__main__':
    main()
