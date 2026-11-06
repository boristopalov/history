"""SQLite storage, and the query that links events to locations.

There is one table. A location fix is just an event with is_fix=1, so a geotagged photo
and a live GPS ping are both usable as evidence of where you were.

Linking happens at query time rather than on ingest. Sources arrive in any order (a photo
backfill can land after the messages it should locate), so a stored link would go stale.
"""

import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from history.models import Batch

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    source    TEXT NOT NULL,
    source_id TEXT NOT NULL,
    ts        REAL NOT NULL,
    end_ts    REAL,
    title     TEXT,
    body      TEXT,
    url       TEXT,
    lat       REAL,
    lon       REAL,
    is_fix    INTEGER NOT NULL DEFAULT 0,
    data      TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (source, source_id)
);
CREATE INDEX IF NOT EXISTS events_ts ON events (ts);
CREATE INDEX IF NOT EXISTS events_fixes ON events (ts) WHERE is_fix = 1;
CREATE INDEX IF NOT EXISTS events_lat ON events (lat) WHERE lat IS NOT NULL;

CREATE TABLE IF NOT EXISTS cursors (
    collector TEXT PRIMARY KEY,
    value     TEXT NOT NULL
);
"""

UPSERT_EVENT = """
INSERT INTO events (source, source_id, ts, end_ts, title, body, url, lat, lon, is_fix, data)
VALUES (:source, :source_id, :ts, :end_ts, :title, :body, :url, :lat, :lon, :is_fix, :data)
ON CONFLICT (source, source_id) DO UPDATE SET
    ts = excluded.ts, end_ts = excluded.end_ts, title = excluded.title, body = excluded.body,
    url = excluded.url, lat = excluded.lat, lon = excluded.lon, is_fix = excluded.is_fix,
    data = excluded.data
"""

EARTH_RADIUS_M = 6_371_000
METERS_PER_DEGREE_LAT = 111_195


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(path: Path) -> None:
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.close()


def ingest(conn: sqlite3.Connection, batch: Batch) -> None:
    rows = [{**e.model_dump(), "data": json.dumps(e.data)} for e in batch.events]
    with conn:  # one transaction: the cursor can never get ahead of the events
        conn.executemany(UPSERT_EVENT, rows)
        if batch.cursor is not None:
            conn.execute(
                "INSERT INTO cursors (collector, value) VALUES (?, ?) "
                "ON CONFLICT (collector) DO UPDATE SET value = excluded.value",
                (batch.collector, batch.cursor),
            )


def cursors(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["collector"]: r["value"] for r in conn.execute("SELECT * FROM cursors")}


def stats(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT source, COUNT(*) AS events, SUM(is_fix) AS fixes, "
        "MIN(ts) AS first_ts, MAX(ts) AS last_ts FROM events GROUP BY source ORDER BY source"
    )
    return [dict(r) for r in rows]


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _nearest_fix(conn: sqlite3.Connection, ts: float, max_gap_s: float) -> dict[str, Any] | None:
    columns = "SELECT lat, lon, source, ts FROM events WHERE is_fix = 1 AND lat IS NOT NULL"
    before = conn.execute(f"{columns} AND ts <= ? ORDER BY ts DESC LIMIT 1", (ts,)).fetchone()
    after = conn.execute(f"{columns} AND ts >= ? ORDER BY ts ASC LIMIT 1", (ts,)).fetchone()
    candidates = [fix for fix in (before, after) if fix and abs(fix["ts"] - ts) <= max_gap_s]
    if not candidates:
        return None
    fix = min(candidates, key=lambda f: abs(f["ts"] - ts))
    return {
        "lat": fix["lat"],
        "lon": fix["lon"],
        "via": fix["source"],
        "gap_s": abs(fix["ts"] - ts),
    }


def _with_location(
    conn: sqlite3.Connection, row: sqlite3.Row, max_gap_s: float
) -> dict[str, Any]:
    event = dict(row)
    event["data"] = json.loads(event["data"])
    event["is_fix"] = bool(event["is_fix"])
    if event["lat"] is not None:
        event["location"] = {
            "lat": event["lat"],
            "lon": event["lon"],
            "via": event["source"],
            "gap_s": 0.0,
        }
    else:
        event["location"] = _nearest_fix(conn, event["ts"], max_gap_s)
    return event


def timeline(
    conn: sqlite3.Connection,
    *,
    start: float | None = None,
    end: float | None = None,
    source: str | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
    max_gap_s: float = 3600,
) -> list[dict[str, Any]]:
    """Events, newest first. `location` is null when no fix is within max_gap_s."""
    where, params = ["1 = 1"], []
    if start is not None:
        where.append("ts >= ?")
        params.append(start)
    if end is not None:
        where.append("ts <= ?")
        params.append(end)
    if source is not None:
        where.append("source = ?")
        params.append(source)
    if q is not None:
        where.append("(title LIKE ? OR body LIKE ? OR url LIKE ?)")
        params += [f"%{q}%"] * 3
    rows = conn.execute(
        f"SELECT * FROM events WHERE {' AND '.join(where)} ORDER BY ts DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return [_with_location(conn, row, max_gap_s) for row in rows]


def _merged_windows(times: list[float], pad: float) -> list[tuple[float, float]]:
    windows: list[tuple[float, float]] = []
    for t in sorted(times):
        if windows and t - pad <= windows[-1][1]:
            windows[-1] = (windows[-1][0], t + pad)
        else:
            windows.append((t - pad, t + pad))
    return windows


def near(
    conn: sqlite3.Connection,
    *,
    lat: float,
    lon: float,
    radius_m: float = 250,
    start: float | None = None,
    end: float | None = None,
    limit: int = 200,
    max_gap_s: float = 3600,
) -> list[dict[str, Any]]:
    """Events that happened within radius_m of a point, newest first."""
    band = radius_m / METERS_PER_DEGREE_LAT
    located_rows = conn.execute(
        "SELECT * FROM events WHERE lat BETWEEN ? AND ?", (lat - band, lat + band)
    ).fetchall()
    in_radius = [r for r in located_rows if haversine_m(lat, lon, r["lat"], r["lon"]) <= radius_m]

    # An event without coordinates can only be here if a fix nearby in time is here.
    candidates = {(r["source"], r["source_id"]): r for r in in_radius}
    fix_times = [r["ts"] for r in in_radius if r["is_fix"]]
    for window_start, window_end in _merged_windows(fix_times, max_gap_s):
        for row in conn.execute(
            "SELECT * FROM events WHERE ts BETWEEN ? AND ? AND lat IS NULL",
            (window_start, window_end),
        ):
            candidates[(row["source"], row["source_id"])] = row

    matches = []
    for row in candidates.values():
        if (start is not None and row["ts"] < start) or (end is not None and row["ts"] > end):
            continue
        event = _with_location(conn, row, max_gap_s)
        found = event["location"]
        # The closest fix may be somewhere else entirely, even with one here in the window.
        if found and haversine_m(lat, lon, found["lat"], found["lon"]) <= radius_m:
            matches.append(event)
    matches.sort(key=lambda e: e["ts"], reverse=True)
    return matches[:limit]
