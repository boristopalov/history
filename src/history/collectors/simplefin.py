"""Card and bank transactions through SimpleFIN Bridge, a paid service for individuals.

The bridge updates about once a day and disables tokens that make too many requests (it
expects 24 a day or fewer). So the cursor records when we last asked, and it's committed
*before* asking: restarts and failures can't add requests, and nothing is lost because each
request covers a window much longer than the gap between requests.

Until a real account is linked, this reads SimpleFIN's public demo account, so the timeline
has transactions to show. Those are invented, and marked `mock` and "[demo]" like health data.

Setup is in the README.
"""

import base64
import logging
import time
import urllib.parse
from collections.abc import Callable, Iterator
from getpass import getpass
from pathlib import Path

import httpx

from history import credentials
from history.collectors.base import Collector, CollectorNotReady
from history.models import Batch, Event

log = logging.getLogger(__name__)

CREDENTIALS = "simplefin"
DEMO_ACCESS_URL = "https://demo:demo@beta-bridge.simplefin.org/simplefin"
MIN_SECONDS_BETWEEN_REQUESTS = 6 * 3600
WINDOW_DAYS = 40  # the bridge warns about requests spanning more than 45 days


def _split_access_url(access_url: str) -> tuple[str, tuple[str, str]]:
    """Separates the credentials from the URL, so they can't end up in an error message."""
    parts = urllib.parse.urlsplit(access_url)
    host = parts.hostname + (f":{parts.port}" if parts.port else "")
    auth = (urllib.parse.unquote(parts.username), urllib.parse.unquote(parts.password))
    return f"{parts.scheme}://{host}{parts.path}", auth


def _timestamp(transaction: dict, account: dict) -> float:
    return (
        transaction.get("transacted_at") or transaction.get("posted") or account["balance-date"]
    )


def _to_event(
    transaction: dict, account: dict, institutions: dict[str, str], demo: bool, key: str
) -> Event:
    transacted_at = transaction.get("transacted_at")
    prefix = "simplefin-demo" if demo else "simplefin"
    return Event(
        source="transactions",
        source_id=f"{prefix}:{account.get('conn_id')}:{account['id']}:{key}",
        ts=_timestamp(transaction, account),
        title=f"[demo] {transaction['description']}" if demo else transaction["description"],
        data={
            **({"mock": True} if demo else {}),
            "amount": transaction["amount"],
            "currency": account.get("currency"),
            "pending": bool(transaction.get("pending")),
            "account": account.get("name"),
            "institution": institutions.get(account.get("conn_id")),
            "date_only": not transacted_at,
        },
    )


def _fetch(http: httpx.Client, access_url: str, now: float, demo: bool) -> list[Event]:
    base_url, auth = _split_access_url(access_url)
    response = http.get(
        f"{base_url}/accounts",
        params={
            "start-date": int(now - WINDOW_DAYS * 86400),
            "pending": 1,
            "version": 2,
        },
        auth=auth,
    )
    if response.status_code == 402:
        raise CollectorNotReady("the SimpleFIN Bridge subscription has lapsed")
    if response.status_code == 403:
        raise CollectorNotReady("SimpleFIN rejected the token; run `hist simplefin-link` again")
    body = response.raise_for_status().json()
    for error in body.get("errlist", []):
        log.warning("simplefin: %s", error.get("msg"))
    institutions = {c["conn_id"]: c["name"] for c in body.get("connections", [])}
    events = []
    for account in body.get("accounts", []):
        # The demo account returns future dates, and `end-date` doesn't reliably exclude them.
        # They aren't lost: the window covers them again once they're in the past.
        transactions = [
            t for t in account.get("transactions", []) if _timestamp(t, account) <= now
        ]
        if demo:
            # Demo rows are a window sliding with the clock, and their ids change on every
            # request. Keying on position makes each refresh overwrite the same rows, where
            # real ids would add a full set of duplicates.
            transactions.sort(key=lambda t: _timestamp(t, account), reverse=True)
        for position, transaction in enumerate(transactions):
            key = str(position) if demo else transaction["id"]
            events.append(_to_event(transaction, account, institutions, demo, key))
    return events


def _batches(
    name: str,
    access_url: str,
    demo: bool,
    http: httpx.Client | None,
    now: Callable[[], float],
    cursor: str | None,
) -> Iterator[Batch]:
    started = now()
    if cursor and started - float(cursor) < MIN_SECONDS_BETWEEN_REQUESTS:
        return
    yield Batch(collector=name, cursor=str(started), events=[])
    if http is not None:
        events = _fetch(http, access_url, started, demo)
    else:
        with httpx.Client(timeout=60) as client:
            events = _fetch(client, access_url, started, demo)
    yield Batch(collector=name, events=events)


def simplefin_collector(
    directory: Path,
    http: httpx.Client | None = None,
    now: Callable[[], float] = time.time,
) -> Collector:
    """Reads the linked account, or the demo if there isn't one. Checked when the daemon starts."""
    stored = credentials.load(directory, CREDENTIALS)
    demo = stored is None
    name = "simplefin.demo" if demo else "simplefin"
    access_url = DEMO_ACCESS_URL if demo else stored["access_url"]
    return Collector(
        name=name,
        source="transactions",
        collect=lambda cursor: _batches(name, access_url, demo, http, now, cursor),
    )


def claim(setup_token: str, http: httpx.Client) -> str:
    """Exchanges a one-time setup token for the access URL."""
    claim_url = base64.b64decode(setup_token.strip()).decode()
    if not claim_url.startswith("https://"):
        raise SystemExit("That doesn't look like a SimpleFIN setup token.")
    response = http.post(claim_url)
    if response.status_code == 403:
        raise SystemExit("That token was already used. Create a new one in SimpleFIN Bridge.")
    return response.raise_for_status().text.strip()


def link(directory: Path) -> None:
    token = getpass("Paste your SimpleFIN setup token (input is hidden): ")
    with httpx.Client(timeout=30) as http:
        access_url = claim(token, http)
    credentials.save(directory, CREDENTIALS, {"access_url": access_url})
    print("SimpleFIN connected. Transactions arrive on the next daemon run.")
