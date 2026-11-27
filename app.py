"""Vercel entrypoint for the frozen dashboard."""
from flask import Flask

from index_engine.frozen_dashboard import create_frozen_app


dashboard = create_frozen_app()
app: Flask = dashboard.server


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050, debug=False)
