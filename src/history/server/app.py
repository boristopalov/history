"""HTTP API and web UI. The daemon writes through /ingest; everything else reads."""

import json
import secrets
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import anthropic
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from history.models import Batch
from history.server import agent, query, store

WEB_DIR = Path(__file__).parent / "static"  # built from web/ by `npm run build`


class QueryRequest(BaseModel):
    sql: str
    limit: int = Field(default=1000, ge=1, le=5000)


class AgentRequest(BaseModel):
    prompt: str = Field(min_length=1)
    # Exactly as the last `done` event returned them. Empty starts a new conversation.
    messages: list[dict[str, Any]] = Field(default_factory=list)
    tz: str = "UTC"


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise HTTPException(status_code=422, detail=f"unknown timezone: {name}") from error


def create_app(
    db_path: Path,
    api_token: str | None = None,
    anthropic_api_key: str | None = None,
    agent_client: anthropic.Anthropic | None = None,
    web_dir: Path = WEB_DIR,
) -> FastAPI:
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

    @app.get("/days")
    def days(conn: Conn, tz: str = "UTC") -> list[dict[str, Any]]:
        return store.days(conn, _zone(tz))

    @app.post("/query")
    def run_query(request: QueryRequest) -> dict[str, Any]:
        try:
            return query.run(db_path, request.sql, limit=request.limit)
        except query.QueryError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/agent")
    def ask_agent(request: AgentRequest) -> StreamingResponse:
        tz = _zone(request.tz)

        def make_client() -> anthropic.Anthropic:
            # With no key given, the SDK looks in the environment.
            return agent_client or anthropic.Anthropic(api_key=anthropic_api_key)

        events = agent.ask(make_client, db_path, request.prompt, request.messages, tz)
        lines = (json.dumps(event) + "\n" for event in events)
        return StreamingResponse(lines, media_type="application/x-ndjson")

    # Last, so that every route above wins over the files.
    if web_dir.is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True))
    else:

        @app.get("/", response_class=PlainTextResponse)
        def web_not_built() -> str:
            return "The web UI isn't built. Run: cd web && npm install && npm run build\n"

    return app
