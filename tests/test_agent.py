"""The agent, driven through /agent with the real SDK against a fake Anthropic API."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from history.config import load_config
from history.models import Batch, Event
from history.server.app import create_app

THINKING = {"type": "thinking", "thinking": "", "signature": "sig-abc"}


def sse(content, stop_reason):
    """The server-sent events for one assistant message."""
    events = [
        {
            "type": "message_start",
            "message": {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-5-5",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        }
    ]
    for index, block in enumerate(content):
        if block["type"] == "text":
            start, delta = {"type": "text", "text": ""}, {"type": "text_delta", "text": block["text"]}
        elif block["type"] == "tool_use":
            start = {"type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}
            delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
        else:
            start = {"type": "thinking", "thinking": "", "signature": ""}
            delta = {"type": "signature_delta", "signature": block["signature"]}
        events += [
            {"type": "content_block_start", "index": index, "content_block": start},
            {"type": "content_block_delta", "index": index, "delta": delta},
            {"type": "content_block_stop", "index": index},
        ]
    events += [
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": 1},
        },
        {"type": "message_stop"},
    ]
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)


def text(value):
    return {"type": "text", "text": value}


def sql_call(sql, id="tool_1"):
    return {"type": "tool_use", "id": id, "name": "run_sql", "input": {"sql": sql}}


class FakeAnthropic:
    """Answers each request with the next scripted response and records what it was sent."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(json.loads(request.content))
        response = self.responses.pop(0)
        if isinstance(response, httpx2.Response):
            return response
        content, stop_reason = response
        return httpx2.Response(
            200, headers={"content-type": "text/event-stream"}, text=sse(content, stop_reason)
        )

    def client(self):
        return anthropic.Anthropic(
            api_key="test",
            max_retries=0,
            http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(self)),
        )


@pytest.fixture
def agent_api(tmp_path):
    def build(*responses):
        fake = FakeAnthropic(*responses)
        client = TestClient(create_app(tmp_path / "history.db", agent_client=fake.client()))
        client.__enter__()
        return client, fake

    return build


def seed(api):
    events = [
        Event(source="location", source_id="f", ts=1000, lat=48.8, lon=2.3, is_fix=True),
        Event(source="messages", source_id="m", ts=1100, body="dinner at 8?"),
    ]
    api.post("/ingest", json=Batch(collector="t", events=events).model_dump()).raise_for_status()


def ask(api, prompt="where was I?", **body):
    response = api.post("/agent", json={"prompt": prompt, **body})
    assert response.status_code == 200
    return [json.loads(line) for line in response.text.splitlines()]


def answer_text(events):
    return "".join(e["text"] for e in events if e["type"] == "text")


def test_a_plain_answer_streams_text_and_ends_with_the_history(agent_api):
    api, fake = agent_api(([text("Paris.")], "end_turn"))
    events = ask(api)
    assert answer_text(events) == "Paris."
    assert events[-1]["type"] == "done"
    assert [m["role"] for m in events[-1]["messages"]] == ["user", "assistant"]


def test_the_agent_queries_the_log_then_answers_from_the_rows(agent_api):
    api, fake = agent_api(
        ([sql_call("SELECT ts, body FROM events WHERE source = 'messages'")], "tool_use"),
        ([text("You were in Paris.")], "end_turn"),
    )
    seed(api)
    events = ask(api, tz="UTC")

    (query,) = [e for e in events if e["type"] == "query"]
    assert query["result"]["rows"] == [[1100, "dinner at 8?"]]
    assert query["result"]["anchors"][0]["location"]["lat"] == 48.8

    tool_result = fake.requests[1]["messages"][-1]["content"][0]
    assert tool_result["tool_use_id"] == "tool_1"
    (row,) = json.loads(tool_result["content"])["rows"]
    assert row["body"] == "dinner at 8?"
    assert row["_local_time"] == "1970-01-01 00:18+00:00"
    assert row["_location"]["gap_s"] == 100
    assert answer_text(events) == "You were in Paris."


def test_a_failed_query_goes_back_to_the_model_so_it_can_fix_it(agent_api):
    api, fake = agent_api(
        ([sql_call("DELETE FROM events")], "tool_use"),
        ([text("I can only read.")], "end_turn"),
    )
    seed(api)
    events = ask(api)
    assert [e["error"] for e in events if e["type"] == "query"] == [
        "Only read-only SELECT queries are allowed."
    ]
    tool_result = fake.requests[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True
    assert events[-1]["type"] == "done"
    assert api.post("/query", json={"sql": "SELECT COUNT(*) FROM events"}).json()["rows"] == [[2]]


def test_a_tool_input_without_sql_is_returned_as_an_error_and_never_run(agent_api):
    malformed = {"type": "tool_use", "id": "tool_1", "name": "run_sql", "input": {"query": 1}}
    api, fake = agent_api(([malformed], "tool_use"), ([text("Sorry.")], "end_turn"))
    events = ask(api)
    assert not [e for e in events if e["type"] == "query"]
    assert fake.requests[1]["messages"][-1]["content"][0]["is_error"] is True


def test_history_round_trips_so_thinking_blocks_replay_unchanged(agent_api):
    api, fake = agent_api(
        ([THINKING, text("First.")], "end_turn"),
        ([text("Second.")], "end_turn"),
    )
    first = ask(api, "one")[-1]["messages"]
    second = ask(api, "two", messages=first)

    sent = fake.requests[1]["messages"]
    assert sent[:2] == first
    assert sent[1]["content"][0] == THINKING
    assert sent[1]["content"][1] == text("First.")
    assert set(sent[1]["content"][1]) == {"type", "text"}
    assert sent[2]["content"].endswith("two")
    assert len(second[-1]["messages"]) == 4


def test_each_question_carries_the_time_in_the_askers_timezone(agent_api):
    api, fake = agent_api(([text("ok")], "end_turn"))
    ask(api, "what day is it?", tz="Asia/Tokyo")
    question = fake.requests[0]["messages"][0]["content"]
    assert "UTC+0900, Asia/Tokyo]" in question
    assert question.endswith("what day is it?")


def test_requests_use_the_expected_model_and_opt_into_fallbacks(agent_api):
    api, fake = agent_api(([text("ok")], "end_turn"))
    ask(api)
    (request,) = fake.requests
    assert request["model"] == "claude-opus-5-5"
    assert request["fallbacks"] == "default"
    assert request["tools"][0]["name"] == "run_sql"


def test_a_refusal_ends_in_an_error_and_returns_no_history(agent_api):
    api, _ = agent_api(([text("partial")], "refusal"))
    events = ask(api)
    assert events[-1] == {"type": "error", "message": "Claude declined to answer that."}
    assert not [e for e in events if e["type"] == "done"]


def test_a_truncated_tool_call_is_not_run(agent_api):
    api, fake = agent_api(([sql_call("SELECT 1")], "max_tokens"))
    events = ask(api)
    assert events[-1]["type"] == "error"
    assert not [e for e in events if e["type"] == "query"]
    assert len(fake.requests) == 1


def test_a_question_that_never_settles_stops_after_the_turn_limit(agent_api):
    from history.server.agent import MAX_TURNS

    api, fake = agent_api(*[([sql_call("SELECT 1")], "tool_use")] * MAX_TURNS)
    events = ask(api)
    assert events[-1]["type"] == "error"
    assert len(fake.requests) == MAX_TURNS


def test_a_rejected_key_is_reported_in_the_stream(agent_api):
    rejected = httpx2.Response(
        401,
        json={"type": "error", "error": {"type": "authentication_error", "message": "bad key"}},
    )
    api, _ = agent_api(rejected)
    assert ask(api)[-1] == {"type": "error", "message": "Anthropic rejected the API key."}


@pytest.mark.parametrize("config_dir_set", [False, True])
def test_missing_credentials_are_reported_in_the_stream(tmp_path, monkeypatch, config_dir_set):
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    if config_dir_set:
        monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path / "no-profile"))
    else:
        monkeypatch.delenv("ANTHROPIC_CONFIG_DIR", raising=False)
    with TestClient(create_app(tmp_path / "history.db")) as api:
        (event,) = ask(api)
    assert event["type"] == "error"
    assert "anthropic_api_key" in event["message"]


@pytest.fixture
def api_keys_sent(monkeypatch):
    """A local stand-in for the Anthropic API. Holds the key of each request it gets."""
    keys = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["content-length"]))
            keys.append(self.headers["authorization"].removeprefix("Bearer "))
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.end_headers()
            self.wfile.write(sse([text("ok")], "end_turn").encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("ANTHROPIC_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    yield keys
    server.shutdown()
    server.server_close()


def test_the_key_from_the_config_file_reaches_the_api(tmp_path, monkeypatch, api_keys_sent):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config_path = tmp_path / "config.toml"
    config_path.write_text('anthropic_api_key = "from-config"\n')
    key = load_config(config_path).anthropic_api_key
    with TestClient(create_app(tmp_path / "history.db", anthropic_api_key=key)) as api:
        assert ask(api)[-1]["type"] == "done"
    assert api_keys_sent == ["from-config"]


def test_the_config_key_wins_over_the_environment(tmp_path, monkeypatch, api_keys_sent):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    with TestClient(create_app(tmp_path / "history.db", anthropic_api_key="from-config")) as api:
        ask(api)
    assert api_keys_sent == ["from-config"]


def test_without_a_config_key_the_environment_is_used(tmp_path, monkeypatch, api_keys_sent):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    with TestClient(create_app(tmp_path / "history.db")) as api:
        ask(api)
    assert api_keys_sent == ["from-env"]


def test_an_unknown_timezone_is_rejected_before_anything_is_spent(agent_api):
    api, fake = agent_api()
    assert api.post("/agent", json={"prompt": "hi", "tz": "Mars/Olympus"}).status_code == 422
    assert fake.requests == []
