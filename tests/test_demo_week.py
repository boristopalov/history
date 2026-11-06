from datetime import datetime

from history.collectors.demo_week import FERRY, demo_week_collector
from history.daemon import run_collectors
from history.models import Event

NOW = datetime(2026, 11, 5, 21, 0)  # a Thursday


def events_at(moment=NOW):
    collector = demo_week_collector(now=lambda: moment)
    return [event for batch in collector.collect(None) for event in batch.events]


def test_everything_is_labelled_and_nothing_is_in_the_future():
    events = events_at()
    assert all(e.data["mock"] and e.title.startswith("[mock] ") for e in events)
    assert all(e.ts <= NOW.timestamp() for e in events)
    assert len({(e.source, e.source_id) for e in events}) == len(events)
    assert {e.source for e in events} == {"location.mock", "receipts", "transactions", "photos"}


def test_a_later_run_keeps_the_same_events():
    earlier = {(e.source, e.source_id): (e.ts, e.title) for e in events_at()}
    later = {(e.source, e.source_id): (e.ts, e.title) for e in events_at(NOW.replace(hour=23))}
    assert all(later[key] == value for key, value in earlier.items())


def test_uber_trips_have_a_matching_charge_and_trail():
    events = events_at()
    trips = [e for e in events if e.source == "receipts"]
    assert len(trips) >= 7
    charges = {
        e.data["amount"]: e for e in events if e.source == "transactions" and "UBER" in e.title
    }
    fixes = [e.ts for e in events if e.is_fix]
    for trip in trips:
        assert trip.data["vendor"] == "uber"
        assert trip.data["pickup"] != trip.data["dropoff"]
        assert f"-{trip.data['amount']}" in charges
        assert min(abs(ts - trip.ts) for ts in fixes) < 15 * 60


def test_a_real_message_gets_placed_on_the_trail_and_says_so(api):
    run_collectors(api, [demo_week_collector(now=lambda: NOW)])
    lunch = next(
        e for e in events_at() if e.source == "transactions" and "FERRY" in e.title
    )
    real = Event(source="messages", source_id="real", ts=lunch.ts, body="hi")
    api.post(
        "/ingest", json={"collector": "t", "events": [real.model_dump()]}
    ).raise_for_status()

    (found,) = api.get("/timeline", params={"source": "messages"}).json()
    assert found["location"]["via"] == "location.mock"
    assert found["location"]["gap_s"] < 20 * 60

    nearby = api.get(
        "/near", params={"lat": FERRY.lat, "lon": FERRY.lon, "radius_m": 300, "limit": 2000}
    ).json()
    assert "real" in {e["source_id"] for e in nearby}
