"""Pulls from every collector on its interval and pushes to the server.

The daemon keeps no state of its own. Cursors live on the server and only advance when a
batch is committed, so if the server is down the source databases act as the queue: the
next run picks up from the last committed cursor.
"""

import logging
import sqlite3
import time

import httpx

from history.collectors import Collector, all_collectors
from history.collectors.base import CollectorNotReady
from history.config import Config

log = logging.getLogger("history.daemon")


def sync(http: httpx.Client, collector: Collector, cursor: str | None) -> int:
    """Pushes everything new from one collector. Returns the number of events sent."""
    sent = 0
    for batch in collector.collect(cursor):
        http.post("/ingest", json=batch.model_dump()).raise_for_status()
        sent += len(batch.events)
    return sent


def run_collectors(http: httpx.Client, collectors: list[Collector]) -> None:
    """Syncs each collector. One failing source never stops the others."""
    cursors = http.get("/cursors").raise_for_status().json()
    for collector in collectors:
        try:
            sent = sync(http, collector, cursors.get(collector.name))
        except sqlite3.OperationalError as error:
            log.warning(
                "%s: %s (does this process have Full Disk Access?)", collector.name, error
            )
        except CollectorNotReady as reason:
            log.warning("%s: %s", collector.name, reason)
        except Exception:
            log.exception("%s: sync failed", collector.name)
        else:
            if sent:
                log.info("%s: pushed %d events", collector.name, sent)


def _client(config: Config) -> httpx.Client:
    return httpx.Client(base_url=config.server_url, headers=config.auth_headers, timeout=60)


def run_forever(config: Config) -> None:
    collectors = [c for c in all_collectors(config) if c.source not in config.disabled]
    last_run: dict[str, float] = {}
    with _client(config) as http:
        while True:
            now = time.monotonic()
            due = [
                c
                for c in collectors
                if c.name not in last_run
                or now - last_run[c.name] >= config.interval_for(c.source)
            ]
            if due:
                try:
                    run_collectors(http, due)
                except httpx.HTTPError as error:
                    log.warning("server unavailable, will retry: %s", error)
                last_run.update({c.name: now for c in due})
            time.sleep(1)


def run_once(config: Config) -> None:
    collectors = [c for c in all_collectors(config) if c.source not in config.disabled]
    with _client(config) as http:
        run_collectors(http, collectors)
