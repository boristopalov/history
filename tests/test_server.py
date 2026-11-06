from history.models import Batch, Event

PARIS = (48.8566, 2.3522)
TOKYO = (35.6762, 139.6503)


def push(api, *events, collector="test", cursor=None):
    batch = Batch(collector=collector, cursor=cursor, events=list(events))
    api.post("/ingest", json=batch.model_dump()).raise_for_status()


def fix(source_id, ts, place, source="location"):
    return Event(source=source, source_id=source_id, ts=ts, lat=place[0], lon=place[1], is_fix=True)


def message(source_id, ts, body="hi"):
    return Event(source="messages", source_id=source_id, ts=ts, body=body)


def only(api, **params):
    (event,) = api.get("/timeline", params=params).json()
    return event


def test_event_is_located_by_the_closest_fix_in_time(api):
    push(api, fix("a", 1000, PARIS), fix("b", 2000, TOKYO), message("m", 1200))
    located = only(api, source="messages")["location"]
    assert (located["lat"], located["lon"]) == PARIS
    assert located["gap_s"] == 200
    assert located["via"] == "location"


def test_event_with_no_fix_within_the_gap_has_no_location(api):
    push(api, fix("a", 1000, PARIS), message("m", 9000))
    assert only(api, source="messages", max_gap_s=3600)["location"] is None


def test_fix_arriving_after_the_event_still_locates_it(api):
    push(api, message("m", 1000))
    assert only(api, source="messages")["location"] is None
    push(api, fix("a", 1010, PARIS, source="photos"))
    assert only(api, source="messages")["location"]["via"] == "photos"


def test_event_with_a_place_keeps_it_but_does_not_locate_others(api):
    planned = Event(source="calendar", source_id="c", ts=1000, lat=TOKYO[0], lon=TOKYO[1])
    push(api, planned, message("m", 1000))
    assert only(api, source="calendar")["location"]["lat"] == TOKYO[0]
    assert only(api, source="messages")["location"] is None


def test_resending_an_event_updates_it_instead_of_duplicating(api):
    push(api, message("m", 1000, body="old"))
    push(api, message("m", 1000, body="new"))
    assert only(api, source="messages")["body"] == "new"


def test_cursor_is_stored_with_the_batch_and_survives_a_batch_without_one(api):
    push(api, message("m", 1), collector="messages", cursor="42")
    push(api, message("n", 2), collector="messages")
    assert api.get("/cursors").json() == {"messages": "42"}


def test_failed_batch_stores_neither_events_nor_cursor(api):
    bad = {
        "collector": "messages",
        "cursor": "99",
        "events": [{"source": "messages", "source_id": "m", "ts": "not a number"}],
    }
    assert api.post("/ingest", json=bad).status_code == 422
    assert api.get("/cursors").json() == {}
    assert api.get("/timeline").json() == []


def test_timeline_filters_by_time_and_text(api):
    push(api, message("a", 100, "lunch"), message("b", 200, "dinner"), message("c", 300, "dinner"))
    assert [e["source_id"] for e in api.get("/timeline", params={"q": "dinner"}).json()] == ["c", "b"]
    assert [e["source_id"] for e in api.get("/timeline", params={"start": 150, "end": 250}).json()] == ["b"]


def test_near_finds_events_by_where_they_happened(api):
    push(
        api,
        fix("paris", 1000, PARIS),
        fix("tokyo", 50_000, TOKYO),
        message("in-paris", 1100),
        message("in-tokyo", 50_100),
    )
    found = api.get("/near", params={"lat": PARIS[0], "lon": PARIS[1], "radius_m": 500}).json()
    assert {e["source_id"] for e in found} == {"paris", "in-paris"}


def test_near_excludes_an_event_whose_closest_fix_is_elsewhere(api):
    push(api, fix("paris", 1000, PARIS), fix("tokyo", 1500, TOKYO), message("m", 1400))
    found = api.get("/near", params={"lat": PARIS[0], "lon": PARIS[1]}).json()
    assert {e["source_id"] for e in found} == {"paris"}
