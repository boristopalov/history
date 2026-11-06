"""MOCK Apple Watch / Health data, so the timeline has this source before the iPhone link.

Every value here is invented. Each event is marked `mock` in its data and "[mock]" in its
title. None of them are location fixes, so they can't affect where other events are placed.

To replace this, set `health_mock = false` and push real samples to /ingest with
`source: "health"` and the same `data` fields.
"""

import random
from collections.abc import Callable, Iterator
from datetime import datetime, time, timedelta

from history.collectors.base import Collector, full_scan
from history.models import Event

DAYS_BACK = 14
WORKOUTS = ("Run", "Walk", "Cycling", "Strength")


def _event(kind: str, key: str, start: datetime, end: datetime | None, title: str, **data) -> Event:
    return Event(
        source="health",
        source_id=f"mock:{kind}:{key}",
        ts=start.timestamp(),
        end_ts=end.timestamp() if end else None,
        title=f"[mock] {title}",
        data={"mock": True, "kind": kind, **data},
    )


def _day_events(day: datetime, now: datetime) -> Iterator[Event]:
    rng = random.Random(day.date().isoformat())  # the same day always gives the same values
    key = day.date().isoformat()

    asleep = day - timedelta(minutes=rng.randint(0, 90))
    awake = day + timedelta(hours=6, minutes=rng.randint(30, 150))
    minutes = int((awake - asleep).total_seconds() // 60)
    sleep = _event(
        "sleep", key, asleep, awake, f"Slept {minutes // 60}h {minutes % 60}m", minutes=minutes
    )

    heart = _event(
        "resting_heart_rate",
        key,
        awake,
        None,
        f"Resting heart rate {(bpm := rng.randint(52, 66))} bpm",
        bpm=bpm,
    )

    workout_start = day + timedelta(hours=rng.randint(7, 19), minutes=rng.randint(0, 59))
    workout_minutes = rng.randint(20, 65)
    workout_end = workout_start + timedelta(minutes=workout_minutes)
    name = rng.choice(WORKOUTS)
    workout = _event(
        "workout",
        key,
        workout_start,
        workout_end,
        f"{name}, {workout_minutes} min",
        workout=name,
        minutes=workout_minutes,
        calories=workout_minutes * rng.randint(6, 11),
    )
    has_workout = rng.random() < 0.5

    steps = [
        _event(
            "steps",
            f"{key}T{hour:02}",
            start := day + timedelta(hours=hour),
            start + timedelta(hours=1),
            f"{(count := rng.randint(100, 1500))} steps",
            steps=count,
        )
        for hour in range(8, 22)
    ]

    candidates = [sleep, heart, *steps, *([workout] if has_workout else [])]
    yield from (e for e in candidates if (e.end_ts or e.ts) <= now.timestamp())


def _events(now: datetime) -> Iterator[Event]:
    today = datetime.combine(now.date(), time.min)
    for days_ago in range(DAYS_BACK, -1, -1):
        yield from _day_events(today - timedelta(days=days_ago), now)


def mock_health_collector(now: Callable[[], datetime] = datetime.now) -> Collector:
    return Collector(
        name="health.mock",
        source="health",
        collect=lambda cursor: full_scan("health.mock", _events(now())),
    )
