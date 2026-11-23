import argparse
from pathlib import Path
from werkzeug.serving import make_server
from repair_shop.app import create_app

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', required=True)
    args = parser.parse_args()
    server = make_server('127.0.0.1', 0, create_app(Path(args.db)), threaded=True)
    print(f'READY http://127.0.0.1:{server.server_port}', flush=True)
    server.serve_forever()
