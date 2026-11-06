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

## Querying

```sh
curl 'localhost:8765/timeline?source=messages&q=dinner&max_gap_s=7200'
curl 'localhost:8765/near?lat=40.7128&lon=-74.0060&radius_m=500'
```

`location` on each result is `{lat, lon, via, gap_s}`, or null when no fix is within
`max_gap_s` (default 3600).

## Configuration

`~/.config/history/config.toml`. Every key is optional.

```toml
interval_seconds = 60                # default for every source
disabled = ["notes"]                 # by source
git_roots = ["~/Desktop/projects"]
git_emails = ["me@example.com"]      # defaults to your global git email
ics_feeds = ["https://…/calendar.ics"]   # Luma, Partiful, anything with an ICS link
transactions_dir = "~/card-exports"  # drop CSV exports from your bank here

[intervals]                          # per-source overrides
messages = 30
```

## Sources

| Source | Read from | Notes |
| --- | --- | --- |
| location | HistoryLocation helper | Only while the Mac is awake |
| photos | Photos.sqlite | Geotagged photos are also location fixes |
| messages | chat.db | Sender is a raw phone number or email |
| browser | Safari, Chrome, Firefox | Every profile |
| calendar | Calendar.sqlitedb, ICS feeds | ICS recurrences are not expanded |
| notes | NoteStore.sqlite | Title and snippet only |
| music | Spotify and Music, via AppleScript | Samples what's playing, so no backfill |
| git | `git log` under `git_roots` | Commits by `git_emails` only |
| transactions | CSV exports | Date only, placed at local noon |

Rows deleted at the source stay here.

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
```
