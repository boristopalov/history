"""Google Calendar, plus ICS feeds for anything that isn't on it."""

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import httpx
import icalendar

from history.collectors.base import Collector, full_scan
from history.collectors.google import gws
from history.models import Event

# Recurring events are expanded by the API, so the window has to be bounded.
DAYS_BACK = 365
DAYS_AHEAD = 180
SKIPPED_CALENDARS = ("#holiday@", "#contacts@")


def _google_time(value: dict[str, str]) -> float:
    if "dateTime" in value:
        return datetime.fromisoformat(value["dateTime"]).timestamp()
    return datetime.fromisoformat(value["date"]).timestamp()  # all-day: local midnight


def _google_event(item: dict[str, Any], calendar: dict[str, Any]) -> Event:
    me = next((a for a in item.get("attendees", []) if a.get("self")), {})
    return Event(
        source="calendar",
        # An invite on two of your calendars has the same id, so it stays one event.
        source_id=f"google:{item['id']}",
        ts=_google_time(item["start"]),
        end_ts=_google_time(item["end"]) if "end" in item else None,
        title=item.get("summary"),
        body=item.get("description"),
        url=item.get("htmlLink"),
        data={
            "place": item.get("location"),
            "all_day": "date" in item["start"],
            "calendar": calendar.get("summary"),
            "response": me.get("responseStatus"),
        },
    )


def _pages(run: Callable[..., dict], command: tuple[str, ...], **params) -> Iterator[dict]:
    token = None
    while True:
        page = run(*command, **params, **({"pageToken": token} if token else {}))
        yield from page.get("items", [])
        token = page.get("nextPageToken")
        if not token:
            return


def _google_events(run: Callable[..., dict], now: datetime) -> Iterator[Event]:
    for calendar in _pages(run, ("calendar", "calendarList", "list")):
        if any(marker in calendar["id"] for marker in SKIPPED_CALENDARS):
            continue
        items = _pages(
            run,
            ("calendar", "events", "list"),
            calendarId=calendar["id"],
            singleEvents=True,
            maxResults=2500,
            timeMin=(now - timedelta(days=DAYS_BACK)).isoformat(),
            timeMax=(now + timedelta(days=DAYS_AHEAD)).isoformat(),
        )
        for item in items:
            if item.get("status") != "cancelled":
                yield _google_event(item, calendar)


def google_calendar_collector(
    run: Callable[..., dict] = gws, now: Callable[[], datetime] = lambda: datetime.now(UTC)
) -> Collector:
    return Collector(
        name="calendar.google",
        source="calendar",
        collect=lambda cursor: full_scan("calendar.google", _google_events(run, now())),
    )


def _ics_timestamp(value: date | datetime) -> float:
    if not isinstance(value, datetime):
        value = datetime.combine(value, time.min)
    return value.timestamp()  # naive values are read as local time, as iCalendar intends


def _read_feed(feed: str) -> bytes:
    if feed.startswith(("http://", "https://")):
        return httpx.get(feed, follow_redirects=True, timeout=30).raise_for_status().content
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
