"""Every data source: the built-in ones, plus any plugins in the config's plugins_dir."""

import importlib.util
import logging
from pathlib import Path

from history.collectors.base import Collector
from history.collectors.browsers import browser_collectors
from history.collectors.calendar import google_calendar_collector, ics_collector
from history.collectors.demo_week import demo_week_collector
from history.collectors.git import git_collector
from history.collectors.health import mock_health_collector
from history.collectors.location import location_collector
from history.collectors.messages import messages_collector
from history.collectors.music import music_collector
from history.collectors.notes import notes_collector
from history.collectors.partiful import partiful_collector
from history.collectors.photos import photos_collector
from history.collectors.receipts import receipts_collector
from history.collectors.simplefin import simplefin_collector
from history.collectors.spotify import spotify_collector
from history.collectors.transactions import transactions_collector
from history.config import Config

__all__ = ["Collector", "all_collectors", "load_plugins"]

log = logging.getLogger(__name__)


def _load_plugin(path: Path, config: Config) -> list[Collector]:
    spec = importlib.util.spec_from_file_location(f"history_plugin_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.collectors(config))


def load_plugins(config: Config) -> list[Collector]:
    """Loads each `*.py` in plugins_dir that defines `collectors(config) -> list[Collector]`.

    A plugin that fails to load is logged and skipped, so it can't take down the others.
    """
    found: list[Collector] = []
    for path in sorted(config.plugins_dir.glob("*.py")):
        try:
            found += _load_plugin(path, config)
        except Exception:
            log.exception("plugin %s failed to load", path.name)
    return found


def all_collectors(config: Config) -> list[Collector]:
    builtin = [
        location_collector(config.location_log),
        photos_collector(),
        messages_collector(),
        *browser_collectors(),
        google_calendar_collector(),
        *(ics_collector(feed, i) for i, feed in enumerate(config.ics_feeds)),
        notes_collector(),
        music_collector(),
        spotify_collector(config.spotify_client_id, config.credentials_dir),
        git_collector(config.git_roots, config.git_emails),
        transactions_collector(config.transactions_dir),
        simplefin_collector(config.credentials_dir, demo=config.simplefin_demo),
        receipts_collector(),
        partiful_collector(),
        *([mock_health_collector()] if config.health_mock else []),
        *([demo_week_collector()] if config.demo_week else []),
    ]
    collectors: dict[str, Collector] = {}
    for collector in builtin + load_plugins(config):
        if collector.name in collectors:  # sharing a name would mean sharing a cursor
            log.error("skipping a second collector named %r", collector.name)
            continue
        collectors[collector.name] = collector
    return list(collectors.values())
