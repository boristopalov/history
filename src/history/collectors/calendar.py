"""Apple Calendar, plus ICS feeds for anything that isn't synced to it (Luma, Partiful)."""

from collections.abc import Iterator
from contextlib import closing
from datetime import date, datetime, time
from pathlib import Path

import httpx
import icalendar

from history.collectors.base import (
    Collector,
    apple_floating_to_unix,
    apple_to_unix,
    full_scan,
    open_readonly,
)
from history.models import Event

DEFAULT_PATH = (
    Path.home() / "Library/Group Containers/group.com.apple.calendar/Calendar.sqlitedb"
)

# OccurrenceCache expands recurring events, for a window around today only. Its
# occurrence_date is always an instant, even for floating events. It also holds one row
# per day of a multi-day event, which is why only recurring items are joined to it.
QUERY = """
SELECT i.UUID, i.summary, i.description, i.url, i.start_tz, i.all_day, i.start_date, i.end_date,
       o.occurrence_date, o.occurrence_end_date,
       l.title AS place, l.address, l.latitude, l.longitude
FROM CalendarItem i
LEFT JOIN OccurrenceCache o ON o.event_id = i.ROWID AND i.has_recurrences = 1
LEFT JOIN Location l ON l.ROWID = i.location_id
WHERE i.hidden = 0 AND i.start_date IS NOT NULL
"""


def _events(path: Path) -> Iterator[Event]:
    with closing(open_readonly(path)) as conn:
        for row in conn.execute(QUERY):
            if row["occurrence_date"] is not None:
                start = apple_to_unix(row["occurrence_date"])
                end = row["occurrence_end_date"] and apple_to_unix(row["occurrence_end_date"])
            else:
                floating = row["start_tz"] == "_float"
                to_unix = apple_floating_to_unix if floating else apple_to_unix
                start = to_unix(row["start_date"])
                end = row["end_date"] and to_unix(row["end_date"])
            located = bool(row["latitude"])
            yield Event(
                source="calendar",
                source_id=f"{row['UUID']}:{start}",
                ts=start,
                end_ts=end,
                title=row["summary"],
                body=row["description"],
                url=row["url"],
                lat=row["latitude"] if located else None,
                lon=row["longitude"] if located else None,
                data={
                    "place": row["place"],
                    "address": row["address"],
                    "all_day": bool(row["all_day"]),
                },
            )


def calendar_collector(path: Path = DEFAULT_PATH) -> Collector:
    def collect(cursor: str | None):
        return full_scan("calendar", _events(path)) if path.exists() else []

    return Collector(name="calendar", source="calendar", collect=collect)


def _ics_timestamp(value: date | datetime) -> float:
    if not isinstance(value, datetime):
        value = datetime.combine(value, time.min)
    return value.timestamp()  # naive values are read as local time, as iCalendar intends


def _read_feed(feed: str) -> bytes:
    if feed.startswith(("http://", "https://")):
        url = feed
        return httpx.get(url, follow_redirects=True, timeout=30).raise_for_status().content
    return Path(feed).expanduser().read_bytes()


def _ics_events(feed: str) -> Iterator[Event]:
    for item in icalendar.Calendar.from_ical(_read_feed(feed)).walk("VEVENT"):
        start = _ics_timestamp(item.decoded("DTSTART"))
        end = _ics_timestamp(item.decoded("DTEND")) if "DTEND" in item else None
        yield Event(
            source="calendar",
            source_id=f"ics:{item.get('UID')}:{start}",
            ts=start,
            end_ts=end,
            title=str(item.get("SUMMARY", "")) or None,
            body=str(item.get("DESCRIPTION", "")) or None,
            url=str(item.get("URL", "")) or None,
            data={"place": str(item.get("LOCATION", "")) or None, "feed": True},
        )


def ics_collector(feed: str, index: int) -> Collector:
    name = f"calendar.ics.{index}"
    return Collector(
        name=name, source="calendar", collect=lambda cursor: full_scan(name, _ics_events(feed))
    )
