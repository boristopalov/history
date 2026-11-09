"""Sources that are reached over HTTP, or derived from other apps' data."""

import base64
import sqlite3
from datetime import datetime

import httpx

from history import credentials
from history.collectors.base import APPLE_EPOCH
from history.collectors.health import mock_health_collector
from history.collectors.partiful import partiful_collector
from history.collectors.spotify import spotify_collector
from history.collectors.simplefin import claim, simplefin_collector
from history.daemon import run_collectors


def make_db(path, script):
    conn = sqlite3.connect(path)
    conn.executescript(script)
    conn.commit()
    conn.close()
    return path


def events_from(collector, cursor=None):
    return [event for batch in collector.collect(cursor) for event in batch.events]


def play(played_at, name="Song"):
    return {
        "played_at": played_at,
        "context": {"uri": "spotify:playlist:1"},
        "track": {
            "id": "t1",
            "name": name,
            "duration_ms": 1000,
            "artists": [{"name": "A"}, {"name": "B"}],
            "album": {"name": "LP"},
            "external_urls": {"spotify": "https://open.spotify.com/track/t1"},
        },
    }


def spotify_api(requests, plays, new_refresh_token=None):
    def handler(request):
        requests.append(request)
        if request.url.path == "/api/token":
            tokens = {"access_token": "access-1"}
            if new_refresh_token:
                tokens["refresh_token"] = new_refresh_token
            return httpx.Response(200, json=tokens)
        return httpx.Response(200, json={"items": plays})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_spotify_pushes_plays_and_resumes_after_the_newest(tmp_path, api):
    credentials.save(tmp_path, "spotify", {"refresh_token": "r1"})
    requests = []
    plays = [play("2026-11-05T10:00:00Z", "Old"), play("2026-11-05T10:05:00.500Z", "New")]
    http = spotify_api(requests, plays)
    run_collectors(api, [spotify_collector("client", tmp_path, http=http)])

    found = api.get("/timeline", params={"source": "music"}).json()
    assert [e["title"] for e in found] == ["New — A, B", "Old — A, B"]
    newest_ms = int(datetime.fromisoformat("2026-11-05T10:05:00.500Z").timestamp() * 1000)
    assert api.get("/cursors").json()["spotify"] == str(newest_ms)

    run_collectors(api, [spotify_collector("client", tmp_path, http=spotify_api(requests, []))])
    assert requests[-1].url.params["after"] == str(newest_ms)
    assert requests[-1].headers["Authorization"] == "Bearer access-1"


def test_spotify_keeps_a_rotated_refresh_token(tmp_path):
    credentials.save(tmp_path, "spotify", {"refresh_token": "r1"})
    http = spotify_api([], [], new_refresh_token="r2")
    events_from(spotify_collector("client", tmp_path, http=http))
    assert credentials.load(tmp_path, "spotify") == {"refresh_token": "r2"}


def test_spotify_does_nothing_until_connected(tmp_path):
    def fail(request):
        raise AssertionError("no request should be made")

    http = httpx.Client(transport=httpx.MockTransport(fail))
    assert events_from(spotify_collector("client", tmp_path, http=http)) == []
    assert events_from(spotify_collector(None, tmp_path, http=http)) == []


ACCESS_URL = "https://user:p%40ss@bridge.test/simplefin"


def simplefin_api(requests, status=200, errlist=()):
    def handler(request):
        requests.append(request)
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(
            200,
            json={
                "errlist": list(errlist),
                "connections": [{"conn_id": "c1", "name": "Some Bank", "org_id": "o",
                                 "sfin_url": "https://bridge.test"}],
                "accounts": [
                    {
                        "id": "a1",
                        "name": "Card",
                        "conn_id": "c1",
                        "currency": "USD",
                        "balance": "100.00",
                        "balance-date": 3000,
                        "transactions": [
                            {"id": "t1", "posted": 1000, "transacted_at": 900,
                             "amount": "-6.50", "description": "BLUE BOTTLE"},
                            {"id": "t2", "posted": 0, "pending": True,
                             "amount": "-9.00", "description": "PENDING CAFE"},
                        ],
                    }
                ],
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def linked(tmp_path):
    credentials.save(tmp_path, "simplefin", {"access_url": ACCESS_URL})
    return tmp_path


def test_simplefin_pushes_transactions(tmp_path, api):
    requests = []
    run_collectors(api, [simplefin_collector(linked(tmp_path), http=simplefin_api(requests))])

    events = {e["title"]: e for e in api.get("/timeline", params={"source": "transactions"}).json()}
    coffee = events["BLUE BOTTLE"]
    assert coffee["ts"] == 900
    assert coffee["data"]["amount"] == "-6.50"
    assert coffee["data"]["institution"] == "Some Bank"
    assert coffee["data"]["date_only"] is False
    pending = events["PENDING CAFE"]
    assert pending["ts"] == 3000
    assert pending["data"]["pending"] is True
    assert pending["data"]["date_only"] is True

    (request,) = requests
    assert request.url.host == "bridge.test" and request.url.path == "/simplefin/accounts"
    assert request.url.params["version"] == "2"
    assert base64.b64decode(request.headers["Authorization"].split()[1]) == b"user:p@ss"


def test_simplefin_stays_within_its_request_budget_across_restarts(tmp_path, api):
    requests = []
    directory = linked(tmp_path)

    def run_at(moment):
        collector = simplefin_collector(
            directory, http=simplefin_api(requests), now=lambda: moment
        )
        run_collectors(api, [collector])

    for minutes in range(0, 360, 15):
        run_at(1_000_000 + minutes * 60)
    assert len(requests) == 1
    run_at(1_000_000 + 6 * 3600)
    assert len(requests) == 2


def test_simplefin_failures_do_not_cause_extra_requests(tmp_path, api):
    requests = []
    directory = linked(tmp_path)
    for minutes in (0, 15, 30):
        collector = simplefin_collector(
            directory,
            http=simplefin_api(requests, status=500),
            now=lambda: 1_000_000 + minutes * 60,
        )
        run_collectors(api, [collector])
    assert len(requests) == 1


def test_simplefin_errors_never_expose_the_password(tmp_path, api, caplog):
    collector = simplefin_collector(linked(tmp_path), http=simplefin_api([], status=500))
    run_collectors(api, [collector])
    assert "sync failed" in caplog.text
    assert "p@ss" not in caplog.text and "p%40ss" not in caplog.text


def test_simplefin_revoked_token_asks_for_a_new_link(tmp_path, api, caplog):
    collector = simplefin_collector(linked(tmp_path), http=simplefin_api([], status=403))
    run_collectors(api, [collector])
    assert "simplefin-link" in caplog.text
    assert "Traceback" not in caplog.text


def test_simplefin_bank_errors_are_surfaced(tmp_path, api, caplog):
    errors = [{"code": "con.auth", "msg": "Reconnect Some Bank"}]
    http = simplefin_api([], errlist=errors)
    run_collectors(api, [simplefin_collector(linked(tmp_path), http=http)])
    assert "Reconnect Some Bank" in caplog.text


def test_simplefin_demo_is_labelled_and_never_in_the_future(tmp_path, api):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "errlist": [],
                "connections": [],
                "accounts": [
                    {
                        "id": "a1",
                        "name": "Savings",
                        "conn_id": "c1",
                        "balance-date": 1000,
                        "transactions": [
                            {"id": "past", "posted": 900, "amount": "-1", "description": "Bait"},
                            {"id": "next", "posted": 1100, "amount": "-2", "description": "Later"},
                        ],
                    }
                ],
            },
        )

    def run_at(moment):
        http = httpx.Client(transport=httpx.MockTransport(handler))
        collector = simplefin_collector(tmp_path, http=http, now=lambda: moment, demo=True)
        run_collectors(api, [collector])
        return api.get("/timeline", params={"source": "transactions"}).json()

    (event,) = run_at(1000)
    assert event["title"] == "[demo] Bait"
    assert event["data"]["mock"] is True
    assert not event["is_fix"]
    assert "simplefin.demo" in api.get("/cursors").json()

    # A future transaction arrives on a later run, once its date has passed.
    assert {e["title"] for e in run_at(1000 + 6 * 3600)} == {"[demo] Bait", "[demo] Later"}


def test_simplefin_demo_refreshes_in_place_when_its_ids_change(tmp_path, api):
    """The real demo account gives every row a new id and timestamp on each request."""

    def run_at(moment):
        def handler(request):
            rows = [
                {"id": str(moment - age), "posted": moment - age, "amount": "-1",
                 "description": "Bait"}
                for age in (100, 200, 300)
            ]
            account = {"id": "a1", "name": "S", "conn_id": "c1", "balance-date": moment,
                       "transactions": rows}
            return httpx.Response(
                200, json={"errlist": [], "connections": [], "accounts": [account]}
            )

        http = httpx.Client(transport=httpx.MockTransport(handler))
        collector = simplefin_collector(tmp_path, http=http, now=lambda: moment, demo=True)
        run_collectors(api, [collector])
        return api.get("/timeline", params={"source": "transactions"}).json()

    run_at(100_000)
    refreshed = run_at(100_000 + 6 * 3600)
    assert len(refreshed) == 3
    assert max(e["ts"] for e in refreshed) == 100_000 + 6 * 3600 - 100


def test_a_linked_account_replaces_the_demo(tmp_path):
    requests = []
    http = simplefin_api(requests)
    collector = simplefin_collector(linked(tmp_path), http=http)
    events = events_from(collector)
    assert collector.name == "simplefin"
    assert requests[0].url.host == "bridge.test"
    assert not any(e.data.get("mock") or e.title.startswith("[demo]") for e in events)


def test_simplefin_uses_the_demo_account_until_linked_when_asked(tmp_path):
    requests = []
    collector = simplefin_collector(tmp_path, http=simplefin_api(requests), demo=True)
    events_from(collector)
    assert collector.name == "simplefin.demo"
    assert requests[0].url.host == "beta-bridge.simplefin.org"


def test_unlinked_simplefin_adds_nothing_by_default(tmp_path, api):
    requests = []
    collector = simplefin_collector(tmp_path, http=simplefin_api(requests))
    run_collectors(api, [collector])
    assert requests == []
    assert api.get("/timeline", params={"source": "transactions"}).json() == []


def test_simplefin_claim_exchanges_a_token_for_an_access_url():
    def handler(request):
        assert request.method == "POST"
        assert str(request.url) == "https://bridge.test/claim/abc"
        return httpx.Response(200, text=ACCESS_URL)

    token = base64.b64encode(b"https://bridge.test/claim/abc").decode()
    http = httpx.Client(transport=httpx.MockTransport(handler))
    assert claim(token, http) == ACCESS_URL


def test_credentials_are_only_readable_by_the_owner(tmp_path):
    credentials.save(tmp_path / "creds", "x", {"a": 1})
    assert (tmp_path / "creds/x.json").stat().st_mode & 0o777 == 0o600


CHAT_SCHEMA = """
CREATE TABLE message (ROWID INTEGER PRIMARY KEY, text TEXT, attributedBody BLOB, date INTEGER,
    is_from_me INTEGER);
INSERT INTO message VALUES (1, 'come! https://partiful.com/e/abc123?c=secret', NULL,
    1000000000000, 0);
INSERT INTO message VALUES (2, 'no link here', NULL, 2000000000000, 0);
INSERT INTO message VALUES (3, 'https://partiful.com/e/gone99', NULL, 3000000000000, 0);
"""


def test_partiful_links_become_events_with_page_details(tmp_path):
    path = make_db(tmp_path / "chat.db", CHAT_SCHEMA)
    asked = []

    def fetch(event_id):
        asked.append(event_id)
        if event_id == "gone99":
            raise httpx.ConnectError("down")
        return {
            "title": "Rooftop",
            "startDate": "2026-11-08T02:00:00.000Z",
            "locationInfo": {"type": "freeform", "value": "Some Bar"},
        }

    good, fallback = events_from(partiful_collector(path, fetch=fetch))
    assert good.title == "Rooftop"
    assert good.ts == datetime.fromisoformat("2026-11-08T02:00:00+00:00").timestamp()
    assert good.data["place"] == "Some Bar"
    assert good.url == "https://partiful.com/e/abc123"
    assert not good.is_fix
    assert (fallback.title, fallback.ts) == ("Partiful invite", 3000 + APPLE_EPOCH)
    assert asked == ["abc123", "gone99"]


def test_mock_health_is_labelled_stable_and_never_in_the_future():
    now = datetime(2026, 11, 5, 15, 30)
    events = events_from(mock_health_collector(now=lambda: now))
    assert events
    assert all(e.data["mock"] and e.title.startswith("[mock] ") for e in events)
    assert all(not e.is_fix and e.lat is None for e in events)
    assert all((e.end_ts or e.ts) <= now.timestamp() for e in events)
    assert {"sleep", "steps", "resting_heart_rate", "workout"} <= {e.data["kind"] for e in events}
    assert len({e.source_id for e in events}) == len(events)

    later = events_from(mock_health_collector(now=lambda: datetime(2026, 11, 5, 21, 0)))
    earlier_by_id = {e.source_id: e.title for e in events}
    assert all(earlier_by_id[e.source_id] == e.title for e in later if e.source_id in earlier_by_id)
