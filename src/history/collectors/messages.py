"""iMessage and SMS, from ~/Library/Messages/chat.db."""

from pathlib import Path

from history.collectors.base import APPLE_EPOCH, Collector, paged
from history.models import Event

DEFAULT_PATH = Path.home() / "Library/Messages/chat.db"

# item_type 0 is a real message rather than a group rename and the like;
# associated_message_type 0 excludes tapbacks.
QUERY = """
SELECT m.ROWID AS id, m.guid, m.text, m.attributedBody, m.date, m.is_from_me, m.service,
       m.cache_has_attachments, h.id AS handle
FROM message m LEFT JOIN handle h ON h.ROWID = m.handle_id
WHERE m.ROWID > :after AND m.item_type = 0 AND m.associated_message_type = 0
ORDER BY m.ROWID LIMIT :limit
"""


def decode_attributed_body(blob: bytes | None) -> str | None:
    """Pulls the plain text out of an NSAttributedString typedstream.

    Recent macOS versions often leave `text` empty and store the body only here. The
    string follows the NSString class marker: a `+` tag, then a length, then UTF-8. The
    length is one byte, or 0x81 + uint16, or 0x82 + uint32 (little-endian).
    """
    if not blob:
        return None
    marker = blob.find(b"NSString")
    if marker == -1:
        return None
    tag = blob.find(b"+", marker)
    if tag == -1:
        return None
    pos = tag + 1
    first = blob[pos]
    if first == 0x81:
        length, pos = int.from_bytes(blob[pos + 1 : pos + 3], "little"), pos + 3
    elif first == 0x82:
        length, pos = int.from_bytes(blob[pos + 1 : pos + 5], "little"), pos + 5
    else:
        length, pos = first, pos + 1
    return blob[pos : pos + length].decode("utf-8", errors="replace")


def _to_event(row) -> Event | None:
    text = row["text"] or decode_attributed_body(row["attributedBody"])
    text = (text or "").replace("￼", "").strip() or None  # U+FFFC marks an attachment
    if text is None and not row["cache_has_attachments"]:
        return None
    return Event(
        source="messages",
        source_id=row["guid"],
        ts=row["date"] / 1_000_000_000 + APPLE_EPOCH,
        title=row["handle"],
        body=text,
        data={
            "from_me": bool(row["is_from_me"]),
            "service": row["service"],
            "has_attachment": bool(row["cache_has_attachments"]),
        },
    )


def messages_collector(path: Path = DEFAULT_PATH) -> Collector:
    return Collector(
        name="messages",
        source="messages",
        collect=lambda cursor: paged("messages", path, QUERY, _to_event, cursor),
    )
