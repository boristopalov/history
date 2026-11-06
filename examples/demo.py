"""See the web UI without touching your real history.

    uv run python examples/demo.py      # then open http://127.0.0.1:8766

It serves the invented week from the demo_week collector out of a temporary database, which
is deleted on exit. Build the UI first: cd web && npm install && npm run build
"""

import tempfile
from pathlib import Path

import uvicorn

from history.collectors.demo_week import demo_week_collector
from history.config import load_config
from history.server import store
from history.server.app import create_app

PORT = 8766


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        db_path = Path(directory) / "demo.db"
        app = create_app(db_path, anthropic_api_key=load_config().anthropic_api_key)
        conn = store.connect(db_path)
        for batch in demo_week_collector().collect(None):
            store.ingest(conn, batch)
        conn.close()
        print(f"Invented data at http://127.0.0.1:{PORT}")
        uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
