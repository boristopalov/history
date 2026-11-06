"""Card transactions, from CSV exports dropped into a folder.

Banks expose no local data, so this reads the CSV export every card site offers. Banks
only give a date, so each transaction is placed at local noon and marked `date_only`.
"""

import csv
import hashlib
import logging
from collections import Counter
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from history.collectors.base import Collector, full_scan
from history.models import Event

log = logging.getLogger(__name__)

DATE_COLUMNS = ("transaction date", "date", "posted date", "post date", "posting date")
DESCRIPTION_COLUMNS = ("description", "merchant", "name", "payee")
AMOUNT_COLUMNS = ("amount", "debit")
DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y")


def _first(row: dict[str, str], columns: tuple[str, ...]) -> str | None:
    return next((row[c].strip() for c in columns if row.get(c, "").strip()), None)


def _noon(text: str) -> float | None:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(hour=12).timestamp()
        except ValueError:
            continue
    return None


def _file_events(path: Path) -> Iterator[Event]:
    seen: Counter[tuple[str, str, str]] = Counter()
    with path.open(newline="", encoding="utf-8-sig") as file:
        for raw in csv.DictReader(file):
            row = {(k or "").strip().lower(): v or "" for k, v in raw.items()}
            date_text = _first(row, DATE_COLUMNS)
            description = _first(row, DESCRIPTION_COLUMNS)
            amount = _first(row, AMOUNT_COLUMNS)
            ts = _noon(date_text) if date_text else None
            if ts is None or description is None or amount is None:
                log.warning("%s: skipped a row with unrecognised columns", path.name)
                continue
            # Two identical coffees on one day are two purchases, but the same purchase in
            # two overlapping exports is one. Numbering repeats within a file does both.
            key = (date_text, description, amount)
            seen[key] += 1
            digest = hashlib.sha256(repr((key, seen[key])).encode()).hexdigest()
            yield Event(
                source="transactions",
                source_id=digest,
                ts=ts,
                title=description,
                data={"amount": amount, "date_only": True, "file": path.name},
            )


def _events(directory: Path) -> Iterator[Event]:
    for path in sorted(directory.glob("*.csv")):
        yield from _file_events(path)


def transactions_collector(directory: Path) -> Collector:
    return Collector(
        name="transactions",
        source="transactions",
        collect=lambda cursor: full_scan("transactions", _events(directory)),
    )
