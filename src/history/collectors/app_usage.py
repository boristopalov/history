"""Which apps were in the foreground on this Mac, from the store behind Screen Time.

iPhone usage isn't in this database. macOS keeps about four weeks of rows.
"""

import plistlib
from functools import cache
from pathlib import Path

from history.collectors.base import Collector, apple_to_unix, paged
from history.models import Event

DEFAULT_PATH = Path.home() / "Library/Application Support/Knowledge/knowledgeC.db"
APP_FOLDERS = (
    Path("/Applications"),
    Path("/System/Applications"),
    Path("/System/Applications/Utilities"),
    Path("/System/Library/CoreServices"),
    Path.home() / "Applications",
)

QUERY = """
SELECT Z_PK AS id, ZUUID, ZVALUESTRING, ZSTARTDATE, ZENDDATE
FROM ZOBJECT
WHERE Z_PK > :after AND ZSTREAMNAME = '/app/usage' AND ZVALUESTRING IS NOT NULL
ORDER BY Z_PK LIMIT :limit
"""


@cache
def _installed_app_names() -> dict[str, str]:
    names = {}
    for folder in APP_FOLDERS:
        for info_path in folder.glob("*.app/Contents/Info.plist"):
            try:
                info = plistlib.loads(info_path.read_bytes())
            except (OSError, plistlib.InvalidFileException):
                continue
            if bundle_id := info.get("CFBundleIdentifier"):
                names[bundle_id] = (
                    info.get("CFBundleDisplayName")
                    or info.get("CFBundleName")
                    or info_path.parents[1].stem
                )
    return names


def _to_event(row) -> Event:
    bundle_id = row["ZVALUESTRING"]
    uuid = row["ZUUID"]
    return Event(
        source="app_usage",
        source_id=uuid.hex() if isinstance(uuid, bytes) else str(uuid),
        ts=apple_to_unix(row["ZSTARTDATE"]),
        end_ts=apple_to_unix(row["ZENDDATE"]) if row["ZENDDATE"] else None,
        title=_installed_app_names().get(bundle_id, bundle_id.split(".")[-1]),
        data={"bundle_id": bundle_id},
    )


def app_usage_collector(path: Path = DEFAULT_PATH) -> Collector:
    return Collector(
        name="app_usage",
        source="app_usage",
        collect=lambda cursor: paged("app_usage", path, QUERY, _to_event, cursor),
    )
