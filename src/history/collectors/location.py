"""Live fixes written by the HistoryLocation helper app, one JSON object per line."""

import json
from collections.abc import Iterator
from pathlib import Path

from history.collectors.base import BATCH_SIZE, Collector
from history.models import Batch, Event


def _to_event(line: bytes) -> Event:
    fix = json.loads(line)
    return Event(
        source="location",
        source_id=str(fix["ts"]),
        ts=fix["ts"],
        lat=fix["lat"],
        lon=fix["lon"],
        is_fix=True,
        data={"accuracy_m": fix.get("accuracy_m")},
    )


def _batches(path: Path, cursor: str | None) -> Iterator[Batch]:
    if not path.exists():
        return
    offset = int(cursor or 0)
    if offset > path.stat().st_size:  # the log was truncated: reading it again is harmless
        offset = 0
    events: list[Event] = []
    with path.open("rb") as log:
        log.seek(offset)
        for line in log:
            if not line.endswith(b"\n"):  # the helper is mid-write; take it next time
                break
            offset += len(line)
            events.append(_to_event(line))
            if len(events) == BATCH_SIZE:
                yield Batch(collector="location", cursor=str(offset), events=events)
                events = []
    if events:
        yield Batch(collector="location", cursor=str(offset), events=events)


def location_collector(path: Path) -> Collector:
    return Collector(
        name="location", source="location", collect=lambda cursor: _batches(path, cursor)
    )
