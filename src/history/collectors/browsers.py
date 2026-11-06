"""Visit history from Safari, Chrome and Firefox, across every profile."""

from pathlib import Path
from urllib.parse import urlsplit

from history.collectors.base import Collector, apple_to_unix, chrome_to_unix, paged
from history.models import Event

SAFARI_QUERY = """
SELECT v.id, v.visit_time, v.title, i.url
FROM history_visits v JOIN history_items i ON i.id = v.history_item
WHERE v.id > :after ORDER BY v.id LIMIT :limit
"""

# The low byte of `transition` is the type; 3 and 4 are subframe loads, not page views.
CHROME_QUERY = """
SELECT v.id, v.visit_time, u.title, u.url
FROM visits v JOIN urls u ON u.id = v.url
WHERE v.id > :after AND (v.transition & 255) NOT IN (3, 4) ORDER BY v.id LIMIT :limit
"""

# visit_type 4 is an embed, 5 and 6 are redirects, 8 is a framed link.
FIREFOX_QUERY = """
SELECT v.id, v.visit_date, p.title, p.url
FROM moz_historyvisits v JOIN moz_places p ON p.id = v.place_id
WHERE v.id > :after AND v.visit_type NOT IN (4, 5, 6, 8) ORDER BY v.id LIMIT :limit
"""


def _collector(name: str, path: Path, query: str, timestamp) -> Collector:
    def to_event(row) -> Event:
        return Event(
            source="browser",
            source_id=f"{name}:{row['id']}",
            ts=timestamp(row),
            title=row["title"] or urlsplit(row["url"]).netloc or row["url"],
            url=row["url"],
            data={"browser": name.split(".")[1]},
        )

    return Collector(
        name=name,
        source="browser",
        collect=lambda cursor: paged(name, path, query, to_event, cursor),
    )


def browser_collectors(home: Path | None = None) -> list[Collector]:
    home = home or Path.home()
    support = home / "Library/Application Support"
    collectors = [
        _collector(
            "browser.safari",
            home / "Library/Safari/History.db",
            SAFARI_QUERY,
            lambda row: apple_to_unix(row["visit_time"]),
        )
    ]
    for path in sorted((support / "Google/Chrome").glob("*/History")):
        if path.parent.name == "Default" or path.parent.name.startswith("Profile"):
            collectors.append(
                _collector(
                    f"browser.chrome.{path.parent.name}",
                    path,
                    CHROME_QUERY,
                    lambda row: chrome_to_unix(row["visit_time"]),
                )
            )
    for path in sorted((support / "Firefox/Profiles").glob("*/places.sqlite")):
        collectors.append(
            _collector(
                f"browser.firefox.{path.parent.name}",
                path,
                FIREFOX_QUERY,
                lambda row: row["visit_date"] / 1_000_000,
            )
        )
    return collectors
