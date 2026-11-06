"""What a collector is, and helpers for reading other apps' SQLite databases."""

import sqlite3
from collections.abc import Callable, Iterable, Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import batched
from pathlib import Path

from history.models import Batch, Event

BATCH_SIZE = 2000
APPLE_EPOCH = 978307200  # 2001-01-01 UTC, the zero point of Core Data timestamps
CHROME_EPOCH_OFFSET = 11644473600  # seconds from 1601-01-01 to 1970-01-01


@dataclass(frozen=True)
class Collector:
    """A pull from one place.

    `collect` receives the last committed cursor and yields batches of anything newer.
    Sources that only ever append use a cursor. Sources whose rows change get rescanned
    in full and yield no cursor; upserts on the server make that safe. Rows deleted at
    the source are not removed here.
    """

    name: str  # unique, and the key the cursor is stored under
    source: str  # category; intervals and `disabled` in the config apply to this
    collect: Callable[[str | None], Iterable[Batch]]


def apple_to_unix(seconds: float) -> float:
    return seconds + APPLE_EPOCH


def apple_floating_to_unix(seconds: float) -> float:
    """Converts an Apple timestamp that holds a local wall-clock time, not an instant."""
    wall_clock = datetime(2001, 1, 1) + timedelta(seconds=seconds)
    return wall_clock.timestamp()  # a naive datetime is read as local time


def chrome_to_unix(microseconds: int) -> float:
    return microseconds / 1_000_000 - CHROME_EPOCH_OFFSET


def open_readonly(path: Path) -> sqlite3.Connection:
    """Opens a database that another app owns. `mode=ro` still sees its uncommitted WAL."""
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def paged(
    name: str,
    path: Path,
    query: str,
    to_event: Callable[[sqlite3.Row], Event | None],
    cursor: str | None,
) -> Iterator[Batch]:
    """Reads an append-only table in id order.

    `query` must select an `id` column, filter on `id > :after`, order by id and apply
    `LIMIT :limit`. Returning None from `to_event` skips a row.
    """
    if not path.exists():
        return
    after = int(cursor or 0)
    with closing(open_readonly(path)) as conn:
        while rows := conn.execute(query, {"after": after, "limit": BATCH_SIZE}).fetchall():
            after = rows[-1]["id"]
            events = [event for row in rows if (event := to_event(row)) is not None]
            yield Batch(collector=name, cursor=str(after), events=events)


def full_scan(name: str, events: Iterable[Event]) -> Iterator[Batch]:
    for chunk in batched(events, BATCH_SIZE):
        yield Batch(collector=name, events=list(chunk))
