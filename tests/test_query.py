from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from history.models import Batch, Event
from history.server import query, store
from history.server.app import create_app

PARIS = (48.8566, 2.3522)


def push(api, *events):
    api.post("/ingest", json=Batch(collector="test", events=list(events)).model_dump()).raise_for_status()


def fix(source_id, ts, place=PARIS):
    return Event(source="location", source_id=source_id, ts=ts, lat=place[0], lon=place[1], is_fix=True)


def message(source_id, ts, body="hi"):
    return Event(source="messages", source_id=source_id, ts=ts, body=body)


def run(api, sql, **params):
    return api.post("/query", json={"sql": sql, **params})


def count_events(api):
    return run(api, "SELECT COUNT(*) FROM events").json()["rows"][0][0]


def test_select_returns_columns_and_rows(api):
    push(api, message("a", 100, "lunch"), message("b", 200, "dinner"))
    result = run(api, "SELECT source_id, body FROM events ORDER BY ts").json()
    assert result["columns"] == ["source_id", "body"]
    assert result["rows"] == [["a", "lunch"], ["b", "dinner"]]
    assert result["truncated"] is False


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM events",
        "DROP TABLE events",
        "UPDATE events SET body = 'x'",
        "INSERT INTO cursors VALUES ('a', 'b')",
        "CREATE TABLE stolen (x)",
        "ATTACH DATABASE '/tmp/other.db' AS other",
        "PRAGMA journal_mode = DELETE",
        "SELECT 1; DELETE FROM events",
    ],
)
def test_anything_but_a_single_read_is_refused_and_changes_nothing(api, sql):
    push(api, message("a", 100))
    response = run(api, sql)
    assert response.status_code == 400
    assert response.json()["detail"]
    assert count_events(api) == 1


def test_syntax_errors_come_back_as_a_message(api):
    response = run(api, "SELEC 1")
    assert response.status_code == 400
    assert "syntax error" in response.json()["detail"]


def test_a_runaway_query_is_stopped(tmp_path):
    store.init_db(tmp_path / "h.db")
    endless = "WITH RECURSIVE c(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM c) SELECT COUNT(*) FROM c"
    with pytest.raises(query.QueryError, match="longer than"):
        query.run(tmp_path / "h.db", endless, timeout_s=0.05)


def test_rows_past_the_limit_are_cut_and_flagged(api):
    push(api, *[message(str(i), i) for i in range(5)])
    result = run(api, "SELECT source_id FROM events", limit=3).json()
    assert len(result["rows"]) == 3
    assert result["truncated"] is True
    assert len(result["anchors"]) == 3


def test_values_json_cannot_hold_still_come_back(api):
    response = run(api, "SELECT x'00ff' AS blob, 9e999 AS infinite")
    assert response.status_code == 200
    assert response.json()["rows"] == [["<2 bytes>", None]]


def test_a_row_with_only_ts_is_located_by_the_nearest_fix(api):
    push(api, fix("f", 1000), message("m", 1200))
    result = run(api, "SELECT ts, body FROM events WHERE source = 'messages'").json()
    (anchor,) = result["anchors"]
    assert anchor["ts"] == 1200
    assert (anchor["location"]["lat"], anchor["location"]["lon"]) == PARIS
    assert anchor["location"]["via"] == "location"
    assert anchor["location"]["gap_s"] == 200


def test_a_row_with_coordinates_is_placed_there(api):
    result = run(api, "SELECT 10.5 AS lat, 20.5 AS LON").json()
    assert result["anchors"] == [
        {"ts": None, "location": {"lat": 10.5, "lon": 20.5, "via": "row", "gap_s": 0.0}}
    ]


def test_a_row_with_ts_and_no_fix_nearby_has_a_time_but_no_place(api):
    push(api, message("m", 1000))
    result = run(api, "SELECT ts FROM events").json()
    assert result["anchors"] == [{"ts": 1000, "location": None}]


def test_rows_with_no_ts_or_place_have_no_anchor(api):
    push(api, message("m", 1000))
    assert run(api, "SELECT source, COUNT(*) FROM events GROUP BY source").json()["anchors"] == [None]


def test_a_ts_too_large_to_be_a_date_is_not_a_moment(api):
    assert run(api, "SELECT 1e30 AS ts").json()["anchors"] == [None]


def test_days_groups_events_by_the_calendar_day_in_the_timezone(api):
    # 2026-11-05 03:30 UTC is still the 4th in New York.
    late_evening = 1793849400
    push(api, fix("f", late_evening), message("m", late_evening + 86400))
    assert api.get("/days", params={"tz": "UTC"}).json() == [
        {"date": "2026-11-05", "events": 1, "fixes": 1},
        {"date": "2026-11-06", "events": 1, "fixes": 0},
    ]
    assert [d["date"] for d in api.get("/days", params={"tz": "America/New_York"}).json()] == [
        "2026-11-04",
        "2026-11-05",
    ]


def test_days_ignores_a_timestamp_no_date_can_hold(api):
    push(api, message("junk", 1e15), message("m", 1793849400))
    assert [d["date"] for d in api.get("/days").json()] == ["2026-11-05"]


def test_days_rejects_an_unknown_timezone(api):
    assert api.get("/days", params={"tz": "Mars/Olympus"}).status_code == 422


def test_the_web_ui_is_served_alongside_the_api(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<title>history</title>")
    with TestClient(create_app(tmp_path / "h.db", web_dir=web)) as client:
        assert "history" in client.get("/").text
        assert client.get("/health").json() == {"status": "ok"}


def test_without_a_build_the_root_says_how_to_make_one(tmp_path):
    with TestClient(create_app(tmp_path / "h.db", web_dir=Path(tmp_path / "missing"))) as client:
        assert "npm run build" in client.get("/").text


def test_query_and_agent_need_the_token_when_one_is_set(tmp_path):
    with TestClient(create_app(tmp_path / "h.db", api_token="secret")) as client:
        assert client.post("/query", json={"sql": "SELECT 1"}).status_code == 401
        assert client.post("/agent", json={"prompt": "hi"}).status_code == 401


def test_the_page_itself_loads_without_the_token_so_it_can_ask_for_one(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<title>history</title>")
    with TestClient(create_app(tmp_path / "h.db", api_token="secret", web_dir=web)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/days").status_code == 401
