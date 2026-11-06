"""Example plugin: every file in ~/Downloads becomes an event.

To enable it: cp examples/downloads.py ~/.config/history/collectors/
"""

from collections.abc import Iterator
from pathlib import Path

from history.sdk import Collector, Config, Event, full_scan


def _events(folder: Path) -> Iterator[Event]:
    for path in folder.iterdir():
        if path.is_file():
            yield Event(
                source="downloads",
                source_id=path.name,
                ts=path.stat().st_mtime,
                title=path.name,
            )


def collectors(config: Config) -> list[Collector]:
    folder = Path.home() / "Downloads"
    return [
        Collector(
            name="downloads",
            source="downloads",
            collect=lambda cursor: full_scan("downloads", _events(folder)),
        )
    ]
