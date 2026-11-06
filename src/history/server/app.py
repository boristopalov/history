"""HTTP API. The daemon writes through /ingest; everything else reads."""

import secrets
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException

from history.models import Batch
from history.server import store


def create_app(db_path: Path, api_token: str | None = None) -> FastAPI:
    store.init_db(db_path)

    def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
        if api_token is None:
            return
        expected = f"Bearer {api_token}".encode()
        if not secrets.compare_digest((authorization or "").encode(), expected):
            raise HTTPException(status_code=401, detail="missing or wrong bearer token")

    app = FastAPI(title="history", dependencies=[Depends(require_token)])

    def get_conn() -> Iterator[sqlite3.Connection]:
        conn = store.connect(db_path)
        try:
            yield conn
        finally:
            conn.close()

    Conn = Annotated[sqlite3.Connection, Depends(get_conn)]

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/cursors")
    def cursors(conn: Conn) -> dict[str, str]:
        return store.cursors(conn)

    @app.post("/ingest")
    def ingest(batch: Batch, conn: Conn) -> dict[str, int]:
        store.ingest(conn, batch)
        return {"ingested": len(batch.events)}

    @app.get("/stats")
    def stats(conn: Conn) -> list[dict[str, Any]]:
        return store.stats(conn)

    @app.get("/timeline")
    def timeline(
        conn: Conn,
        start: float | None = None,
        end: float | None = None,
        source: str | None = None,
        q: str | None = None,
        limit: int = 200,
        offset: int = 0,
        max_gap_s: float = 3600,
    ) -> list[dict[str, Any]]:
        return store.timeline(
            conn,
            start=start,
            end=end,
            source=source,
            q=q,
            limit=limit,
            offset=offset,
            max_gap_s=max_gap_s,
        )

    @app.get("/near")
    def near(
        conn: Conn,
        lat: float,
        lon: float,
        radius_m: float = 250,
        start: float | None = None,
        end: float | None = None,
        limit: int = 200,
        max_gap_s: float = 3600,
    ) -> list[dict[str, Any]]:
        return store.near(
            conn,
            lat=lat,
            lon=lon,
            radius_m=radius_m,
            start=start,
            end=end,
            limit=limit,
            max_gap_s=max_gap_s,
        )

    return app
