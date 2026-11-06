import base64
from datetime import UTC, datetime
from email.message import EmailMessage

import pytest

from history.collectors.base import Collector, CollectorNotReady
from history.collectors.calendar import google_calendar_collector
from history.collectors.receipts import parse_receipt, receipts_collector
from history.daemon import run_collectors

NOW = datetime(2026, 11, 5, tzinfo=UTC)


def receipt(sender, subject, html_lines):
    message = EmailMessage()
    message["From"] = sender
    message["Subject"] = subject
    body = "".join(f"<tr><td>{line}</td></tr>" for line in html_lines)
    message.set_content(f"<html><head><style>x</style></head><table>{body}</table></html>", subtype="html")
    return message.as_bytes()


UBER = receipt(
    "Uber Receipts <noreply@uber.com>",
    "Your Saturday evening trip with Uber",
    ["Total", "$23.45", "March 1, 2026", "Thanks for riding, B", "Total", "$23.45", "Trip fare",
     "$20.00", "Visa ••••1234", "UberX", "7.21 miles | 18 min", "7:02 PM",
     "1 Main St, Washington, DC 20001, US", "7:20 PM", "2 Oak Ave, Mc Lean, VA 22101, US",
     "Report lost item"],
)
LYFT = receipt(
    "Lyft Ride Receipt <no-reply@lyftmail.com>",
    "Your ride with Sam on January 4",
    ["Thanks for riding with Sam!", "Standard fare (12.10mi, 24m 10s)", "$18.00", "DC City Fee",
     "$1.00", "Apple Pay (Visa)", "$19.00", "Pickup 1:15 AM", "3 Elm St NW, Washington, DC",
     "Drop-off 1:40 AM", "4 Pine Ct, Mc Lean, VA", "Tip driver"],
)
LYFT_BIKE = receipt(
    "Lyft <no-reply@lyftmail.com>",
    "Your Lyft Bike ride on July 2",
    ["Bike ride total: $6.20 Bank Checking *1234 - Details inside", "Unlock fee", "$1.00",
     "Your Trip", "West St & Chambers St", "Start", "4:10 pm", "Ave A & E 7 St", "End", "4:31 pm"],
)
DOORDASH = receipt(
    "DoorDash <no-reply@doordash.com>",
    "Order Confirmation for B from Noodle Bar",
    ["Thanks for your", "order, B", "Paid with Visa Ending in 1234", "Noodle Bar",
     "Total: $31.10", "Your receipt", "9 Main St, Riverhead, NY", "Subtotal", "$25.00",
     "Total Charged", "$31.10"],
)
MARKETING = receipt("Uber <uber@uber.com>", "Take 50% off your next 2 orders", ["Total $1.00"])
LOOKALIKE = receipt("x <a@notuber.com>", "Your Saturday evening trip with Uber", ["Total", "$1.00"])


def test_uber_receipt():
    assert parse_receipt(UBER) == {
        "subject": "Your Saturday evening trip with Uber",
        "vendor": "uber",
        "kind": "ride",
        "amount": "23.45",
        "product": "UberX",
        "pickup_time": "7:02 PM",
        "pickup": "1 Main St, Washington, DC 20001, US",
        "dropoff_time": "7:20 PM",
        "dropoff": "2 Oak Ave, Mc Lean, VA 22101, US",
    }


def test_lyft_receipt_takes_the_amount_paid():
    fields = parse_receipt(LYFT)
    assert fields["amount"] == "19.00"
    assert fields["pickup"] == "3 Elm St NW, Washington, DC"
    assert (fields["pickup_time"], fields["dropoff_time"]) == ("1:15 AM", "1:40 AM")
    assert fields["dropoff"] == "4 Pine Ct, Mc Lean, VA"


def test_lyft_bike_receipt():
    fields = parse_receipt(LYFT_BIKE)
    assert fields["vendor"] == "lyft_bike"
    assert fields["amount"] == "6.20"
    assert fields["pickup"] == "West St & Chambers St"
    assert fields["dropoff"] == "Ave A & E 7 St"


def test_doordash_receipt():
    fields = parse_receipt(DOORDASH)
    assert (fields["merchant"], fields["amount"]) == ("Noodle Bar", "31.10")


def test_marketing_and_lookalike_senders_are_not_receipts():
    assert parse_receipt(MARKETING) is None
    assert parse_receipt(LOOKALIKE) is None


def fake_gmail(messages, seen_queries=None):
    """`messages` are (id, seconds, raw email), oldest first, like a mailbox."""

    def run(*command, **params):
        if command[-1] == "list":
            if seen_queries is not None:
                seen_queries.append(params["q"])
            after = int(params["q"].rsplit("after:", 1)[1])
            newest_first = [m for m in reversed(messages) if m[1] >= after]
            return {"messages": [{"id": m[0]} for m in newest_first]}
        message = next(m for m in messages if m[0] == params["id"])
        assert params["format"] == "raw"
        encoded = base64.urlsafe_b64encode(message[2]).decode().rstrip("=")
        return {"id": message[0], "internalDate": str(message[1] * 1000), "raw": encoded}

    return run


def test_receipts_reach_the_server_without_the_email_text_and_resume(api):
    start = int(NOW.timestamp())
    messages = [("a", start - 200, UBER), ("b", start - 100, MARKETING)]
    queries = []
    collect = lambda run: receipts_collector(run=run, now=lambda: NOW)
    run_collectors(api, [collect(fake_gmail(messages, queries))])

    (event,) = api.get("/timeline", params={"source": "receipts"}).json()
    assert event["title"] == "Your Saturday evening trip with Uber"
    assert event["data"]["pickup"] == "1 Main St, Washington, DC 20001, US"
    assert event["body"] is None
    assert "1234" not in str(event)
    assert event["ts"] == start - 200
    assert api.get("/cursors").json()["receipts"] == str(start - 100)

    messages.append(("c", start, LYFT))
    run_collectors(api, [collect(fake_gmail(messages, queries))])
    assert queries[-1].endswith(f"after:{start - 100}")
    assert len(api.get("/timeline", params={"source": "receipts"}).json()) == 2


def fake_calendar(pages):
    def run(*command, **params):
        if command[1] == "calendarList":
            return {"items": [
                {"id": "me@gmail.com", "summary": "Mine"},
                {"id": "shared@group.calendar.google.com", "summary": "Shared"},
                {"id": "en.usa#holiday@group.v.calendar.google.com", "summary": "Holidays"},
            ]}
        assert params["singleEvents"] is True
        return pages(params)

    return run


def test_google_calendar_pages_dedupes_and_skips_cancelled_and_holidays(api):
    asked = []
    invite = {
        "id": "shared-invite",
        "summary": "Dinner",
        "location": "Some Bar",
        "start": {"dateTime": "2026-11-08T19:00:00-05:00"},
        "end": {"dateTime": "2026-11-08T21:00:00-05:00"},
        "attendees": [{"self": True, "responseStatus": "accepted"}, {"email": "x@y.z"}],
    }
    all_day = {"id": "trip", "summary": "Trip", "start": {"date": "2026-11-09"},
               "end": {"date": "2026-11-10"}}
    cancelled = {"id": "gone", "status": "cancelled", "start": {"date": "2026-11-09"}}

    def pages(params):
        asked.append(params["calendarId"])
        if params["calendarId"].startswith("shared"):
            return {"items": [invite]}
        if "pageToken" not in params:
            return {"items": [invite, cancelled], "nextPageToken": "next"}
        return {"items": [all_day]}

    collector = google_calendar_collector(run=fake_calendar(pages), now=lambda: NOW)
    run_collectors(api, [collector])

    events = {e["title"]: e for e in api.get("/timeline", params={"source": "calendar"}).json()}
    assert set(events) == {"Dinner", "Trip"}
    dinner = events["Dinner"]
    assert dinner["ts"] == datetime.fromisoformat("2026-11-08T19:00:00-05:00").timestamp()
    assert dinner["data"]["place"] == "Some Bar"
    assert dinner["data"]["response"] == "accepted"
    assert not dinner["is_fix"]
    assert events["Trip"]["data"]["all_day"] is True
    assert datetime.fromtimestamp(events["Trip"]["ts"]) == datetime(2026, 11, 9)
    assert not any("holiday" in calendar for calendar in asked)


def test_missing_login_is_reported_without_stopping_other_sources(api, caplog):
    def needs_login(cursor):
        raise CollectorNotReady("run gws auth login")

    def healthy(cursor):
        return []

    run_collectors(api, [Collector("a", "a", needs_login), Collector("b", "b", healthy)])
    assert "run gws auth login" in caplog.text
    assert "Traceback" not in caplog.text


def test_expired_login_becomes_not_ready(monkeypatch):
    import subprocess

    from history.collectors import google

    expired = subprocess.CompletedProcess(
        [], 1, stdout='{"error": {"code": 401, "message": "invalid_grant"}}', stderr=""
    )
    monkeypatch.setattr(google.subprocess, "run", lambda *a, **k: expired)
    with pytest.raises(CollectorNotReady, match="gws auth login"):
        google.gws("gmail", "users", "getProfile", userId="me")
