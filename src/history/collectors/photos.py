"""Apple Photos. Geotagged photos double as location fixes, going back years."""

from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

from history.collectors.base import Collector, apple_to_unix, full_scan, open_readonly
from history.models import Event

DEFAULT_PATH = Path.home() / "Pictures/Photos Library.photoslibrary/database/Photos.sqlite"

QUERY = """
SELECT ZUUID, ZFILENAME, ZDATECREATED, ZLATITUDE, ZLONGITUDE, ZKIND
FROM ZASSET WHERE ZTRASHEDSTATE = 0 AND ZDATECREATED IS NOT NULL
"""


def _has_coordinates(lat: float | None, lon: float | None) -> bool:
    # Photos stores -180 for "no location".
    return lat is not None and lon is not None and -90 <= lat <= 90 and (lat, lon) != (0, 0)


def _events(path: Path) -> Iterator[Event]:
    with closing(open_readonly(path)) as conn:
        for row in conn.execute(QUERY):
            located = _has_coordinates(row["ZLATITUDE"], row["ZLONGITUDE"])
            yield Event(
                source="photos",
                source_id=row["ZUUID"],
                ts=apple_to_unix(row["ZDATECREATED"]),
                title=row["ZFILENAME"],
                lat=row["ZLATITUDE"] if located else None,
                lon=row["ZLONGITUDE"] if located else None,
                is_fix=located,
                data={"kind": "video" if row["ZKIND"] == 1 else "photo"},
            )


def photos_collector(path: Path = DEFAULT_PATH) -> Collector:
    def collect(cursor: str | None):
        return full_scan("photos", _events(path)) if path.exists() else []

    return Collector(name="photos", source="photos", collect=collect)
