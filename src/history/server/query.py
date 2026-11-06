"""Read-only SQL over the event log, for the web UI and the agent.

Queries come from a text box and from a model, so the database enforces the limits rather
than a check on the SQL text. The connection is opened read-only, and an authorizer allows
only reads, which also rules out ATTACH (reaching other files) and PRAGMA.
"""

import math
import sqlite3
import time
from pathlib import Path
from typing import Any

from history.server import store

ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}
PROGRESS_EVERY_N_OPS = 10_000


class QueryError(Exception):
    """The query could not run. The message is meant for whoever wrote it."""


def _authorize(action: int, *_: Any) -> int:
    return sqlite3.SQLITE_OK if action in ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def _connect(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.set_authorizer(_authorize)
    return conn


def _json_safe(value: Any) -> Any:
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if isinstance(value, float) and not math.isfinite(value):
        return None  # JSON has no Infinity or NaN
    return value


def _number(row: sqlite3.Row, index: int | None) -> float | None:
    value = None if index is None else row[index]
    return float(value) if isinstance(value, int | float) and math.isfinite(value) else None


def _anchor(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    columns: dict[str, int],
    max_gap_s: float,
) -> dict[str, Any] | None:
    """When and where a result row happened, if its columns say.

    A row with lat and lon is placed there. A row with only ts is placed the way every
    other event is, by the nearest fix in time.
    """
    ts = _number(row, columns.get("ts"))
    if ts is not None and not 0 <= ts <= store.MAX_TS:
        ts = None
    lat, lon = _number(row, columns.get("lat")), _number(row, columns.get("lon"))
    if lat is not None and lon is not None and abs(lat) <= 90 and abs(lon) <= 180:
        location = {"lat": lat, "lon": lon, "via": "row", "gap_s": 0.0}
    elif ts is not None:
        location = store.nearest_fix(conn, ts, max_gap_s)
    else:
        location = None
    if ts is None and location is None:
        return None
    return {"ts": ts, "location": location}


def run(
    path: Path,
    sql: str,
    *,
    limit: int = 1000,
    timeout_s: float = 10,
    max_gap_s: float = 3600,
) -> dict[str, Any]:
    """Run one SELECT. `anchors` lines up with `rows`: see `_anchor`."""
    conn = _connect(path)
    try:
        deadline = time.monotonic() + timeout_s
        conn.set_progress_handler(lambda: time.monotonic() > deadline, PROGRESS_EVERY_N_OPS)
        try:
            cursor = conn.execute(sql)
            fetched = cursor.fetchmany(limit + 1)
        except sqlite3.Error as error:
            code = getattr(error, "sqlite_errorname", None)
            if code == "SQLITE_AUTH":
                raise QueryError("Only read-only SELECT queries are allowed.") from error
            if code == "SQLITE_INTERRUPT":
                raise QueryError(f"The query took longer than {timeout_s:g} seconds.") from error
            raise QueryError(str(error)) from error
        conn.set_progress_handler(None, 0)

        names = [column[0] for column in cursor.description or []]
        cursor.close()
        columns = {name.lower(): index for index, name in enumerate(names)}
        rows = fetched[:limit]
        return {
            "columns": names,
            "rows": [[_json_safe(value) for value in row] for row in rows],
            "anchors": [_anchor(conn, row, columns, max_gap_s) for row in rows],
            "truncated": len(fetched) > limit,
        }
    finally:
        conn.close()
