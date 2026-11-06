"""Uber, Lyft and DoorDash, from their receipt emails in Gmail.

None of them offer a personal API, but every trip and order sends an email with the fare and,
for rides, the pickup and drop-off. Only the fields parsed here are kept, never the email text.
The email formats are undocumented: anything that can't be parsed is left as None.

The event's timestamp is when the email arrived, close to when a trip ended. Pickup and
drop-off times are kept as printed, because the emails don't say which timezone they're in.
"""

import base64
import email
import html
import re
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from email import policy
from typing import Any

from history.collectors.base import Collector
from history.collectors.google import gws
from history.models import Batch, Event

FIRST_RUN_DAYS_BACK = 365
BATCH_SIZE = 50

SEARCH = (
    "from:(uber.com OR lyftmail.com OR doordash.com) "
    'subject:("trip with Uber" OR "Your ride with" OR "Lyft Bike ride" OR "Uber Eats order" '
    'OR "Order Confirmation" OR receipt)'
)

# (vendor, kind, sender domain, subject). Everything else from these senders is marketing.
RULES = (
    ("uber", "ride", "uber.com", re.compile(r"^Your .* trip with Uber", re.I)),
    ("uber_eats", "delivery", "uber.com", re.compile(r"^Your .*Uber Eats order", re.I)),
    ("lyft", "ride", "lyftmail.com", re.compile(r"^Your ride with", re.I)),
    ("lyft_bike", "ride", "lyftmail.com", re.compile(r"^Your Lyft Bike ride", re.I)),
    ("doordash", "delivery", "doordash.com", re.compile(r"^(Order Confirmation|.*receipt)", re.I)),
)

MONEY = re.compile(r"\$\s*([\d,]+\.\d{2})")
CLOCK = re.compile(r"\b(\d{1,2}:\d{2}\s*[AP]M)\b", re.I)
DISTANCE = re.compile(r"[\d.]+\s*(miles|mi|kilometers|km)\b.*\|", re.I)


def email_lines(raw: bytes) -> tuple[email.message.EmailMessage, list[str]]:
    """Reduces an email to its visible lines of text."""
    message = email.message_from_bytes(raw, policy=policy.default)
    part = message.get_body(preferencelist=("html", "plain"))
    try:
        text = part.get_content() if part else ""
    except (LookupError, ValueError):  # an unknown charset
        text = ""
    text = re.sub(r"(?is)<(style|script|head)\b.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|td|table|h\d)>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"[ \t ͏‌​]+", " ", text)
    return message, [line.strip() for line in text.split("\n") if line.strip()]


def _money_after(lines: list[str], label: str) -> str | None:
    """The first amount on the line starting with `label`, or on the line after it."""
    for i, line in enumerate(lines):
        if line.lower().startswith(label.lower()):
            for candidate in lines[i : i + 2]:
                if found := MONEY.search(candidate):
                    return found.group(1)
    return None


def _clock(line: str) -> str | None:
    found = CLOCK.search(line)
    return found.group(1) if found else None


def _parse_uber(lines: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {"amount": _money_after(lines, "Total")}
    for i, line in enumerate(lines):
        if DISTANCE.search(line) and len(lines) > i + 4:
            parsed |= {
                "product": lines[i - 1] if i else None,
                "pickup_time": _clock(lines[i + 1]),
                "pickup": lines[i + 2],
                "dropoff_time": _clock(lines[i + 3]),
                "dropoff": lines[i + 4],
            }
            break
    return parsed


def _parse_lyft(lines: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for i, line in enumerate(lines[:-1]):
        if line.startswith("Pickup") and "pickup" not in parsed:
            parsed |= {"pickup_time": _clock(line), "pickup": lines[i + 1]}
            # The amount paid is the last one listed above the route.
            amounts = [m for text in lines[:i] for m in MONEY.findall(text)]
            parsed["amount"] = amounts[-1] if amounts else None
        elif line.startswith("Drop-off") and "dropoff" not in parsed:
            parsed |= {"dropoff_time": _clock(line), "dropoff": lines[i + 1]}
    return parsed


def _parse_lyft_bike(lines: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {"amount": _money_after(lines, "Bike ride total")}
    for i, line in enumerate(lines):
        if line == "Start" and 0 < i and len(lines) > i + 1:
            parsed |= {"pickup": lines[i - 1], "pickup_time": _clock(lines[i + 1])}
        elif line == "End" and 0 < i and len(lines) > i + 1:
            parsed |= {"dropoff": lines[i - 1], "dropoff_time": _clock(lines[i + 1])}
    return parsed


def _parse_doordash(lines: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {"amount": _money_after(lines, "Total Charged")}
    for i, line in enumerate(lines):
        if line.startswith("Total:") and i:
            parsed["merchant"] = lines[i - 1]
            parsed["amount"] = parsed["amount"] or _money_after(lines, "Total:")
            break
    return parsed


def _parse_uber_eats(lines: list[str]) -> dict[str, Any]:
    return {"amount": _money_after(lines, "Total")}


PARSERS = {
    "uber": _parse_uber,
    "uber_eats": _parse_uber_eats,
    "lyft": _parse_lyft,
    "lyft_bike": _parse_lyft_bike,
    "doordash": _parse_doordash,
}


def parse_receipt(raw: bytes) -> dict[str, Any] | None:
    """The fields of a receipt email, or None if the email isn't a receipt."""
    message, lines = email_lines(raw)
    subject = str(message.get("Subject", ""))
    sender = str(message.get("From", "")).lower().rstrip("> ")
    domain = sender.rsplit("@", 1)[-1]
    for vendor, kind, sender_domain, pattern in RULES:
        if (domain == sender_domain or domain.endswith(f".{sender_domain}")) and pattern.search(
            subject
        ):
            return {"subject": subject, "vendor": vendor, "kind": kind} | PARSERS[vendor](lines)
    return None


def _to_event(message: dict[str, Any]) -> Event | None:
    raw = base64.urlsafe_b64decode(message["raw"] + "=" * (-len(message["raw"]) % 4))
    fields = parse_receipt(raw)
    if fields is None:
        return None
    subject = fields.pop("subject")
    return Event(
        source="receipts",
        source_id=f"gmail:{message['id']}",
        ts=int(message["internalDate"]) / 1000,
        title=subject,
        data=fields,
    )


def _message_ids(run: Callable[..., dict], query: str) -> list[str]:
    ids: list[str] = []
    token = None
    while True:
        params = {"pageToken": token} if token else {}
        page = run(
            "gmail", "users", "messages", "list", userId="me", q=query, maxResults=500, **params
        )
        ids += [message["id"] for message in page.get("messages", [])]
        token = page.get("nextPageToken")
        if not token:
            return ids


def _batches(
    run: Callable[..., dict], now: Callable[[], datetime], cursor: str | None
) -> Iterator[Batch]:
    since = cursor or str(int((now() - timedelta(days=FIRST_RUN_DAYS_BACK)).timestamp()))
    # Gmail lists newest first. Going oldest first means a cursor never skips anything.
    ids = list(reversed(_message_ids(run, f"{SEARCH} after:{since}")))
    for start in range(0, len(ids), BATCH_SIZE):
        messages = [
            run("gmail", "users", "messages", "get", userId="me", id=message_id, format="raw")
            for message_id in ids[start : start + BATCH_SIZE]
        ]
        newest = max(int(message["internalDate"]) for message in messages) // 1000
        events = [event for message in messages if (event := _to_event(message)) is not None]
        yield Batch(collector="receipts", cursor=str(newest), events=events)


def receipts_collector(
    run: Callable[..., dict] = gws, now: Callable[[], datetime] = lambda: datetime.now(UTC)
) -> Collector:
    return Collector(
        name="receipts", source="receipts", collect=lambda cursor: _batches(run, now, cursor)
    )
