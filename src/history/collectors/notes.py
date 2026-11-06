"""Apple Notes. Only the title and snippet: full bodies are gzipped protobufs."""

from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

from history.collectors.base import Collector, apple_to_unix, full_scan, open_readonly
from history.models import Event

DEFAULT_PATH = Path.home() / "Library/Group Containers/group.com.apple.notes/NoteStore.sqlite"

QUERY = """
SELECT ZIDENTIFIER, ZTITLE1, ZSNIPPET, COALESCE(ZCREATIONDATE3, ZCREATIONDATE1) AS created,
       ZMODIFICATIONDATE1 AS modified
FROM ZICCLOUDSYNCINGOBJECT
WHERE ZTITLE1 IS NOT NULL AND ZNOTEDATA IS NOT NULL AND ZMARKEDFORDELETION IS NOT 1
  AND COALESCE(ZCREATIONDATE3, ZCREATIONDATE1) IS NOT NULL
"""


def _events(path: Path) -> Iterator[Event]:
    with closing(open_readonly(path)) as conn:
        for row in conn.execute(QUERY):
            yield Event(
                source="notes",
                source_id=row["ZIDENTIFIER"],
                ts=apple_to_unix(row["created"]),
                title=row["ZTITLE1"],
                body=row["ZSNIPPET"],
                data={"modified_ts": apple_to_unix(row["modified"]) if row["modified"] else None},
            )


def notes_collector(path: Path = DEFAULT_PATH) -> Collector:
    def collect(cursor: str | None):
        return full_scan("notes", _events(path)) if path.exists() else []

    return Collector(name="notes", source="notes", collect=collect)
