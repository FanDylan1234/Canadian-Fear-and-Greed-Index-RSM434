"""Run the saved evaluation edition locally, with no Bloomberg connection."""
import argparse
from .dashdesign import create_app
from .frozen_snapshot import FrozenService


def create_frozen_app(server=None):
    return create_app(service=FrozenService(), server=server)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--offline", action="store_true", help="This edition is always offline")
    args = parser.parse_args()
    create_frozen_app().run(host="127.0.0.1", port=args.port, debug=False)
