import argparse
from .server import serve

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Local Migration Studio MVP')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    serve(port=args.port)
