"""Flask application entrypoint used by Vercel."""
from flask import Flask

from index_engine.frozen_dashboard import create_frozen_app


app: Flask = Flask(__name__)
dashboard = create_frozen_app(server=app)
