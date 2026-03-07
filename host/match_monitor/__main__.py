"""Match monitor entry point. Usage: python -m host.match_monitor [--port 8510] [--output-dir ...]"""

import argparse
from .receiver import run_server


def main():
    parser = argparse.ArgumentParser(description='FRC Robot Match Monitor - Log Receiver')
    parser.add_argument('--port', type=int, default=8510,
                        help='Port to listen on (default: 8510, use 5810 on FRC network)')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Directory to save received logs (default: ~/Documents/robotlogs)')
    parser.add_argument('--bind', type=str, default='0.0.0.0',
                        help='Address to bind to (default: 0.0.0.0)')
    args = parser.parse_args()
    run_server(args.bind, args.port, args.output_dir)


if __name__ == '__main__':
    main()
