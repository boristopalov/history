"""Partiful invites. There's no API, but invites arrive as texts with a link to a public page.

An invite doesn't mean you went, so these are never location fixes. If the page can't be read
(its format is undocumented, and some are password protected), the event falls back to the
time the text arrived, with just the link.
"""

import json
import re
from collections.abc import Callable
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

import httpx

from history.collectors.base import APPLE_EPOCH, Collector, paged
from history.collectors.messages import DEFAULT_PATH, decode_attributed_body
from history.models import Event

LINK = re.compile(r"partiful\.com/e/([A-Za-z0-9]+)")
PAGE_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

QUERY = """
SELECT ROWID AS id, text, attributedBody, date, is_from_me FROM message
WHERE ROWID > :after
  AND (text LIKE '%partiful.com/e/%'
       OR instr(attributedBody, CAST('partiful.com/e/' AS BLOB)) > 0)
ORDER BY ROWID LIMIT :limit
"""


def fetch_event_page(event_id: str) -> dict[str, Any] | None:
    # The invite's `?c=` code identifies you to Partiful, so it's deliberately left off.
    response = httpx.get(
        f"https://partiful.com/e/{event_id}",
        headers={"User-Agent": "Mozilla/5.0"},
        follow_redirects=True,
        timeout=20,
    )
    found = PAGE_DATA.search(response.text) if response.status_code == 200 else None
    return json.loads(found.group(1))["props"]["pageProps"].get("event") if found else None


def _place(event: dict[str, Any]) -> str | None:
    info = event.get("locationInfo") or {}
    maps = info.get("mapsInfo") or {}
    address = ", ".join(maps.get("addressLines") or [])
    # Hosts can hide the exact address from people who haven't RSVPed.
    return (
        info.get("value")  # hosts can also type in free text
        or maps.get("name")
        or address
        or maps.get("approximateLocation")
        or info.get("neighborhood")
    )


def partiful_collector(
    path: Path = DEFAULT_PATH,
    fetch: Callable[[str], dict[str, Any] | None] = fetch_event_page,
) -> Collector:
    @cache
    def details(event_id: str) -> dict[str, Any]:
        try:
            return fetch(event_id) or {}
        except (httpx.HTTPError, ValueError, KeyError):
            return {}

    def to_event(row) -> Event | None:
        text = row["text"] or decode_attributed_body(row["attributedBody"]) or ""
        link = LINK.search(text)
        if link is None:
            return None
        event_id = link.group(1)
        page = details(event_id)
        sent = row["date"] / 1_000_000_000 + APPLE_EPOCH
        start = page.get("startDate")
        end = page.get("endDate")
        return Event(
            source="events",
            source_id=f"partiful:{event_id}",
            ts=datetime.fromisoformat(start).timestamp() if start else sent,
            end_ts=datetime.fromisoformat(end).timestamp() if end else None,
            title=page.get("title") or "Partiful invite",
            url=f"https://partiful.com/e/{event_id}",
            data={"platform": "partiful", "place": _place(page), "invite_ts": sent},
        )

    return Collector(
        name="partiful",
        source="events",
        collect=lambda cursor: paged("partiful", path, QUERY, to_event, cursor),
    )
