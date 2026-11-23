"""Run Repair Desk on this computer. Does not read .env or contact APIs."""
import argparse
from pathlib import Path
import sys

if __package__ in ('', None):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from repair_shop.app import create_app

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Repair Desk — local workshop management')
    parser.add_argument('--port', type=int, default=5001)
    args = parser.parse_args()
    print(f'Repair Desk is available at http://127.0.0.1:{args.port}', flush=True)
    create_app().run(host='127.0.0.1', port=args.port, debug=False, use_reloader=False, threaded=True)
