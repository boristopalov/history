"""iMessage and SMS, from ~/Library/Messages/chat.db, named using your Contacts."""

import re
import sqlite3
from contextlib import closing
from pathlib import Path

from history.collectors.base import APPLE_EPOCH, Collector, open_readonly, paged
from history.models import Event

DEFAULT_PATH = Path.home() / "Library/Messages/chat.db"
ADDRESS_BOOKS = Path.home() / "Library/Application Support/AddressBook/Sources"

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


def _contact_key(handle: str) -> str:
    """Phone numbers match on their last 10 digits, since country codes are stored unevenly."""
    if "@" in handle:
        return handle.lower()
    return re.sub(r"\D", "", handle)[-10:]


def load_contacts(address_books: list[Path]) -> dict[str, str]:
    contacts: dict[str, str] = {}
    for path in address_books:
        try:
            with closing(open_readonly(path)) as conn:
                rows = conn.execute(
                    """
                    SELECT r.ZFIRSTNAME AS first, r.ZLASTNAME AS last, p.ZFULLNUMBER AS handle
                    FROM ZABCDPHONENUMBER p JOIN ZABCDRECORD r ON r.Z_PK = p.ZOWNER
                    UNION ALL
                    SELECT r.ZFIRSTNAME, r.ZLASTNAME, e.ZADDRESS
                    FROM ZABCDEMAILADDRESS e JOIN ZABCDRECORD r ON r.Z_PK = e.ZOWNER
                    """
                ).fetchall()
        except sqlite3.Error:
            continue
        for row in rows:
            name = " ".join(part for part in (row["first"], row["last"]) if part)
            if name and row["handle"]:
                contacts[_contact_key(row["handle"])] = name
    return contacts


def _to_event(row, contacts: dict[str, str]) -> Event | None:
    text = row["text"] or decode_attributed_body(row["attributedBody"])
    text = (text or "").replace("￼", "").strip() or None  # U+FFFC marks an attachment
    if text is None and not row["cache_has_attachments"]:
        return None
    return Event(
        source="messages",
        source_id=row["guid"],
        ts=row["date"] / 1_000_000_000 + APPLE_EPOCH,
        title=contacts.get(_contact_key(row["handle"] or ""), row["handle"]) or "Me",
        body=text,
        data={
            "handle": row["handle"],
            "from_me": bool(row["is_from_me"]),
            "service": row["service"],
            "has_attachment": bool(row["cache_has_attachments"]),
        },
    )


def messages_collector(
    path: Path = DEFAULT_PATH, address_books: list[Path] | None = None
) -> Collector:
    def collect(cursor: str | None):
        books = sorted(ADDRESS_BOOKS.glob("*/AddressBook-v22.abcddb"))
        contacts = load_contacts(books if address_books is None else address_books)
        return paged("messages", path, QUERY, lambda row: _to_event(row, contacts), cursor)

    return Collector(name="messages", source="messages", collect=collect)
