# history

Links where you were with what you were doing: photos, messages, browsing, calendar, notes,
music, commits and card transactions, all on one timeline.

```
 source databases           daemon                       server
 ┌────────────────┐    ┌──────────────┐  POST /ingest  ┌───────────────┐
 │ chat.db        │    │ collectors   │───────────────▶│ FastAPI       │
 │ Photos.sqlite  │───▶│ pull on each │  GET /cursors  │ SQLite        │
 │ places.sqlite… │    │ interval     │◀───────────────│               │
 └────────────────┘    └──────────────┘                │ GET /timeline │
 ┌────────────────┐           ▲                        │ GET /near     │
 │ HistoryLocation│ JSONL ────┘      POST /ingest      │               │
 │ (Swift helper) │       anything else ──────────────▶│               │
 └────────────────┘       (phone, scripts, any language)└──────────────┘
```

- **One table.** Every source becomes an `Event`. A location fix is an event with `is_fix`
  set, so geotagged photos and live pings are the same kind of evidence.
- **Linking happens at query time.** Each event gets the nearest fix in time, and the response
  says how far away that fix was (`gap_s`). Sources can arrive in any order.
- **Cursors live on the server** and commit in the same transaction as their events. The daemon
  keeps no state: if the server is down, the source databases are the queue.

## Running it

```sh
uv sync
uv run hist server         # http://127.0.0.1:8765, API docs at /docs
uv run hist daemon         # pulls every minute; add --once for a single pass
uv run hist status

./macos/build.sh && open macos/build/HistoryLocation.app   # live location; allow the prompt
```

Run the daemon from a terminal that has **Full Disk Access** (System Settings → Privacy &
Security), because the source databases are protected. Under launchd, the Python binary itself
would need that access. Polling Spotify or Music asks for Automation permission on first use.

The database holds your messages in plain text. It lives in `~/.local/share/history/`, outside
the repo.

## The web UI

```sh
cd web && npm install && npm run build   # once, and after changing the UI
uv run hist server                       # then open http://127.0.0.1:8765
```

The map shows a day, and the timeline scrubs or plays through it. A solid line joins fixes up
to 30 minutes apart. A dashed line means a longer gap, where nothing says what route you took,
so the marker waits at the last fix and turns hollow rather than gliding along it.

The panel on the right searches everything, as a **SQL** box or as **Ask**, an agent that
writes the queries for you. Any result row with a `ts` goes on the map, placed by the nearest
fix, and clicking the row jumps to that moment.

Ask uses `claude-opus-5-5`, and needs `anthropic_api_key` in the config, or `ANTHROPIC_API_KEY`
in the environment. The config wins if both are set. Ask can only read. Each question costs API
credits, up to 12 rounds of queries.

Two things leave this machine. Your questions and the rows the agent reads go to Anthropic,
which can include your messages. And map tiles come from OpenFreeMap, which can see which
areas you look at.

To look around without real data, run `uv run python examples/demo.py`. To work on the UI, run
`npm run dev` in `web/`, which reloads as you edit and uses the server on port 8765.

## Querying

```sh
curl 'localhost:8765/timeline?source=messages&q=dinner&max_gap_s=7200'
curl 'localhost:8765/near?lat=40.7128&lon=-74.0060&radius_m=500'
```

`location` on each result is `{lat, lon, via, gap_s}`, or null when no fix is within
`max_gap_s` (default 3600).

`POST /query` runs one read-only SELECT, with a 10 second limit:

```sh
curl localhost:8765/query -H 'content-type: application/json' \
  -d '{"sql": "SELECT ts, body FROM events WHERE body LIKE '"'"'%dinner%'"'"' LIMIT 5"}'
```

`anchors` lines up with `rows`: `{ts, location}` for each row that has a `ts`, or `lat` and
`lon`, and null for the others.

## Configuration

`~/.config/history/config.toml`. Every key is optional.

```toml
interval_seconds = 60                # default for every source
disabled = ["notes"]                 # by source
git_roots = ["~/Desktop/projects"]
git_emails = ["me@example.com"]      # defaults to your global git email
ics_feeds = ["https://…/calendar.ics"]   # Luma, Partiful, anything with an ICS link
transactions_dir = "~/card-exports"  # drop CSV exports from your bank here
anthropic_api_key = "sk-ant-…"       # for Ask in the web UI; chmod 600 this file

[intervals]                          # per-source overrides
messages = 30
```

## Sources

| Source | Read from | Notes |
| --- | --- | --- |
| location | HistoryLocation helper | Only while the Mac is awake |
| app_usage | knowledgeC.db (behind Screen Time) | This Mac only, not your iPhone |
| photos | Photos.sqlite | Geotagged photos are also location fixes |
| messages | chat.db | Names come from your Contacts |
| browser | Safari, Chrome, Firefox | Every profile |
| calendar | Google Calendar, ICS feeds | Past year and next 6 months; holiday calendars skipped; ICS recurrences are not expanded |
| notes | NoteStore.sqlite | Title and snippet only |
| music | Spotify Web API, Apple Music | Spotify covers every device; see setup below |
| receipts | Uber, Lyft, DoorDash emails in Gmail | Fares, pickups and drop-offs; see below |
| events | Partiful links in your texts | Invites, not proof you went |
| health | **Mock data** | Invented, and labelled `[mock]`; see below |
| git | `git log` under `git_roots` | Commits by `git_emails` only |
| transactions | SimpleFIN Bridge, or CSV exports | About a day behind; time of day often missing |

Rows deleted at the source stay here.

### Connecting accounts

**Spotify.** Create an app at developer.spotify.com with the redirect URI
`http://127.0.0.1:8888/callback`. Spotify requires the app owner to have Premium. Put the
client ID in the config as `spotify_client_id`, then run `uv run hist spotify-login`. The API
only returns your last 50 plays, so older listening isn't available this way.

**Cards and banks.** Sign up for [SimpleFIN Bridge](https://bridge.simplefin.org) ($15 a year),
connect your banks there, and create a setup token. Then run `uv run hist simplefin-link` and
paste it. The bridge updates about once a day, so transactions are not instant, and it keeps
at most 90 days. The daemon asks at most every 6 hours, because too many requests can get the
token disabled.

Tokens are stored in `~/.config/history/credentials/`, readable only by you.

**Google (Gmail and Calendar).** Both go through the `gws` CLI, read-only. Sign in with the
account that holds your calendar. This replaces any scopes `gws` already has, so add other
services to the list if you use them.

```sh
gws auth login --readonly --services gmail,calendar
```

**Uber, Lyft and DoorDash.** None has a personal API, so `receipts` reads their receipt emails.
It looks back a year on the first run, and keeps only the parsed fields, not the email text.

**Luma.** Its API needs a paid plan and appears to cover only events you host. Add an ICS link
to `ics_feeds` if you have one.

**Apple Health.** `health` is invented data, so that the source exists before the iPhone link
does. To replace it, set `health_mock = false` and push real samples to `/ingest` with
`source: "health"`.

### Mock data

`demo_week` invents the past week around San Francisco: a location trail, Uber trips, card
purchases and geotagged photos that all agree with each other. It's on by default so a demo has
linked data. Everything fake says `[mock]` in its title and `mock` in `data`. Real messages and
browsing get placed on the fake trail, and show `via: location.mock`.

Until you link a real account, `transactions` also shows SimpleFIN's public demo account, whose
rows say `[demo]`. Linking replaces it after a daemon restart.

To go back to real data, set `demo_week = false` and `health_mock = false`, then delete the rows:

```sh
sqlite3 ~/.local/share/history/history.db "DELETE FROM events WHERE json_extract(data, '$.mock') = 1"
```

## Writing a collector

There are two ways to connect, and neither touches this repo.

### Over HTTP, in any language

An external collector needs two calls. `examples/push_fix.sh` is a complete one in curl.

```
GET  /cursors    → {"<collector>": "<cursor>", …}
POST /ingest     {"collector": "phone", "cursor": "abc", "events": [ … ]}
```

- `collector` is a unique name. `cursor` is any string you want back on your next run, stored
  in the same transaction as the events. Leave it out if you don't need one.
- Each event needs `source`, `source_id` and `ts` (unix seconds). The optional fields are
  `end_ts`, `title`, `body`, `url`, `lat`, `lon`, `is_fix` and `data` (any JSON object).
- Re-sending a `source_id` updates that event, so retries are always safe.
- Set `is_fix: true` only if the event proves you were at `lat`/`lon` at `ts`. Fixes are what
  locate every other event. An event with a planned place, like a calendar invite, keeps its
  `lat`/`lon` with `is_fix` false.
- `source` is free-form, and a new value needs no server change.

The full schema is at `/docs`.

### As a Python plugin, run by the daemon

Drop a file in `~/.config/history/collectors/` that defines `collectors(config)`. The daemon
schedules it, tracks its cursor and isolates its failures. Plugins run with the daemon's
access, including Full Disk Access, so only install code you trust.
`examples/downloads.py` is a complete one.

```python
from history.sdk import Collector, Event, full_scan

def collectors(config):
    def collect(cursor):
        events = [Event(source="steps", source_id="2026-11-05", ts=1793923200, title="8000 steps")]
        return full_scan("steps", events)

    return [Collector(name="steps", source="steps", collect=collect)]
```

`collect(cursor)` yields batches. Use `full_scan` when rows can change or the source is small,
and `paged` for a large append-only SQLite table. Import only from `history.sdk`.

### Connecting from another machine

The server listens on localhost only. To accept remote collectors, set `host` and `api_token`
in the config, and send `Authorization: Bearer <token>`. The server refuses to bind beyond
localhost without a token. The token travels unencrypted over plain HTTP, so use a private
network such as Tailscale.

## Tests

```sh
uv run --group dev pytest
cd web && npm test
```
