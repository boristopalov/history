"""The two ways for someone else's code to connect."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from history.collectors import all_collectors, load_plugins
from history.config import Config
from history.daemon import run_collectors
from history.server.app import create_app

EXAMPLES = Path(__file__).parent.parent / "examples"

PLUGIN = """
from history.sdk import Collector, Event, full_scan

def collectors(config):
    events = [Event(source="steps", source_id="day-1", ts=100, title="8000 steps")]
    return [Collector(name="steps", source="steps",
                      collect=lambda cursor: full_scan("steps", events))]
"""


def config_for(tmp_path):
    plugins = tmp_path / "collectors"
    plugins.mkdir()
    return Config(plugins_dir=plugins, git_roots=[], git_emails=[])


def test_a_dropped_in_plugin_reaches_the_server(tmp_path, api):
    config = config_for(tmp_path)
    (config.plugins_dir / "steps.py").write_text(PLUGIN)
    run_collectors(api, load_plugins(config))
    (event,) = api.get("/timeline", params={"source": "steps"}).json()
    assert event["title"] == "8000 steps"


def test_shipped_example_plugin_loads(tmp_path):
    config = config_for(tmp_path)
    shutil.copy(EXAMPLES / "downloads.py", config.plugins_dir)
    assert [c.name for c in load_plugins(config)] == ["downloads"]


def test_a_broken_plugin_does_not_affect_the_rest(tmp_path):
    config = config_for(tmp_path)
    (config.plugins_dir / "a_broken.py").write_text("raise RuntimeError('nope')")
    (config.plugins_dir / "steps.py").write_text(PLUGIN)
    assert [c.name for c in load_plugins(config)] == ["steps"]


def test_a_plugin_cannot_share_a_cursor_with_a_builtin(tmp_path):
    config = config_for(tmp_path)
    (config.plugins_dir / "clash.py").write_text(PLUGIN.replace('name="steps"', 'name="messages"'))
    names = [c.name for c in all_collectors(config)]
    assert names.count("messages") == 1


def test_external_collector_needs_only_plain_json_over_http(api):
    batch = {
        "collector": "phone",
        "cursor": "abc",
        "events": [
            {"source": "location", "source_id": "1", "ts": 500, "lat": 1.5, "lon": 2.5, "is_fix": True},
            {"source": "workouts", "source_id": "1", "ts": 510, "title": "Run", "data": {"km": 5}},
        ],
    }
    assert api.post("/ingest", json=batch).json() == {"ingested": 2}
    assert api.get("/cursors").json()["phone"] == "abc"
    (workout,) = api.get("/timeline", params={"source": "workouts"}).json()
    assert workout["data"] == {"km": 5}
    assert workout["location"]["via"] == "location"


@pytest.mark.parametrize(
    "event",
    [
        {"source": "x", "source_id": "1", "ts": 1, "is_fix": True},
        {"source": "x", "source_id": "1", "ts": 1, "lat": 1.0},
        {"source": "x", "source_id": "1", "ts": 1, "lat": -180.0, "lon": 0.0},
        {"source": "", "source_id": "1", "ts": 1},
    ],
)
def test_malformed_events_are_rejected(api, event):
    response = api.post("/ingest", json={"collector": "c", "events": [event]})
    assert response.status_code == 422


def test_token_is_enforced_when_configured(tmp_path):
    with TestClient(create_app(tmp_path / "h.db", api_token="s3cret")) as client:
        assert client.get("/timeline").status_code == 401
        wrong = {"Authorization": "Bearer nope"}
        assert client.get("/timeline", headers=wrong).status_code == 401
        right = {"Authorization": "Bearer s3cret"}
        assert client.get("/timeline", headers=right).status_code == 200
