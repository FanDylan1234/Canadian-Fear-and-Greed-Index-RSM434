"""Vercel WSGI entrypoint: read the committed snapshot, never fetch market data."""
from index_engine.frozen_dashboard import create_frozen_app

dashboard = create_frozen_app()
app = dashboard.server

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8050, debug=False)
