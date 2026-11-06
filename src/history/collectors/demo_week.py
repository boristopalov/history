"""MOCK: a made-up week around San Francisco, so a demo shows what linked data looks like.

Everything here is invented, including the "home" and "office". Each event is marked `mock` in
its data and "[mock]" in its title. It covers what's missing from real data right now: where
you were, plus the Uber trips, purchases and photos that go with it. Trips, purchases and
locations are generated together, so they agree with each other.

Unlike other mock data, the location trail is made of real fixes (from `location.mock`), so
real messages and browsing get placed on it, and show `via: location.mock`. Set
`demo_week = false` and delete the mock rows to go back to real locations only.
"""

import math
import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from history.collectors.base import Collector, full_scan
from history.models import Event

DAYS_BACK = 7
STAY_FIX_MINUTES = 20
TRAVEL_FIX_MINUTES = 3
UBER_ABOVE_KM = 2.0


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lon: float
    address: str
    merchant: str | None = None
    spend: tuple[int, int] = (0, 0)
    photo: bool = False


HOME = Place("Home", 37.7762, -122.4243, "Hayes St & Laguna St, San Francisco, CA")
OFFICE = Place("Office", 37.7825, -122.3995, "2nd St & Folsom St, San Francisco, CA")
CAFE = Place(
    "Blue Bottle Coffee", 37.7826, -122.4075, "66 Mint St, San Francisco, CA",
    "BLUE BOTTLE COFFEE", (5, 12),
)
FERRY = Place(
    "Ferry Building", 37.7955, -122.3937, "1 Ferry Building, San Francisco, CA",
    "FERRY PLAZA MARKET", (14, 28), True,
)
PARK = Place(
    "Dolores Park", 37.7596, -122.4269, "Dolores St & 19th St, San Francisco, CA", photo=True
)
DINNER = Place(
    "Tartine Manufactory", 37.7617, -122.4115, "595 Alabama St, San Francisco, CA",
    "TARTINE MANUFACTORY", (32, 78), True,
)
BAR = Place(
    "Mission bar", 37.7650, -122.4216, "16th St & Valencia St, San Francisco, CA",
    "MISSION BAR & GRILL", (12, 38),
)

WEEKDAY = ((CAFE, 8.5), (OFFICE, 9.25), (FERRY, 12.5), (OFFICE, 13.5), (DINNER, 18.75))
WEEKEND = ((CAFE, 10.0), (PARK, 12.0), (FERRY, 15.0), (DINNER, 19.0))


def _km(a: Place, b: Place) -> float:
    x = math.radians(b.lon - a.lon) * math.cos(math.radians(a.lat))
    return 6371 * math.hypot(x, math.radians(b.lat - a.lat))


def _part_of_day(moment: datetime) -> str:
    if moment.hour < 12:
        return "morning"
    return "afternoon" if moment.hour < 17 else "evening"


def _clock(moment: datetime) -> str:
    return moment.strftime("%-I:%M %p")


class _Day:
    def __init__(self, day: datetime):
        self.day = day
        self.key = day.date().isoformat()
        self.rng = random.Random(f"demo-{self.key}")  # the same day is always the same
        self.count = 0
        self.events: list[Event] = []

    def add(self, source: str, moment: datetime, title: str | None, **fields) -> None:
        self.count += 1
        data = {"mock": True} | fields.pop("data", {})
        self.events.append(
            Event(
                source=source,
                source_id=f"mock:{self.key}:{self.count}",
                ts=moment.timestamp(),
                title=f"[mock] {title}",
                data=data,
                **fields,
            )
        )

    def fix(self, moment: datetime, lat: float, lon: float, place: str) -> None:
        self.add(
            "location.mock", moment, place, lat=lat, lon=lon, is_fix=True, data={"place": place}
        )

    def charge(self, moment: datetime, merchant: str, amount: float) -> None:
        self.add(
            "transactions",
            moment,
            merchant,
            data={
                "amount": f"-{amount:.2f}",
                "currency": "USD",
                "pending": False,
                "account": "Mock Card",
                "institution": "Mock Bank",
                "date_only": False,
            },
        )

    def stay(self, place: Place, arrive: datetime, leave: datetime) -> None:
        moment = arrive
        while moment < leave:
            lat = place.lat + self.rng.uniform(-0.0002, 0.0002)
            lon = place.lon + self.rng.uniform(-0.0002, 0.0002)
            self.fix(moment, lat, lon, place.name)
            moment += timedelta(minutes=STAY_FIX_MINUTES)
        if place.merchant:
            spent = self.rng.uniform(*place.spend)
            self.charge(arrive + timedelta(minutes=self.rng.randint(4, 15)), place.merchant, spent)
        if place.photo and self.rng.random() < 0.6:
            taken = arrive + timedelta(minutes=self.rng.randint(5, 30))
            self.add(
                "photos",
                taken,
                f"IMG_{self.rng.randint(1000, 9999)}.HEIC",
                lat=place.lat,
                lon=place.lon,
                is_fix=True,
                data={"kind": "photo"},
            )

    def travel(self, start: Place, end: Place, leave: datetime) -> datetime:
        km = _km(start, end)
        by_uber = km > UBER_ABOVE_KM
        minutes = km / (0.35 if by_uber else 0.08) + self.rng.uniform(1, 4)
        arrive = leave + timedelta(minutes=minutes)
        steps = max(int(minutes // TRAVEL_FIX_MINUTES), 1)
        for step in range(1, steps):
            share = step / steps
            self.fix(
                leave + timedelta(minutes=step * TRAVEL_FIX_MINUTES),
                start.lat + (end.lat - start.lat) * share,
                start.lon + (end.lon - start.lon) * share,
                f"En route to {end.name}",
            )
        if by_uber:
            fare = 7.5 + km * 2.4 + self.rng.uniform(0, 5)
            self.add(
                "receipts",
                arrive + timedelta(minutes=2),
                f"Your {leave:%A} {_part_of_day(leave)} trip with Uber",
                data={
                    "vendor": "uber",
                    "kind": "ride",
                    "amount": f"{fare:.2f}",
                    "product": "UberX",
                    "pickup_time": _clock(leave),
                    "pickup": start.address,
                    "dropoff_time": _clock(arrive),
                    "dropoff": end.address,
                },
            )
            self.charge(arrive + timedelta(minutes=3), "UBER *TRIP", fare)
        return arrive


def _day_events(day: datetime) -> list[Event]:
    plan = _Day(day)
    stops = WEEKDAY if day.weekday() < 5 else WEEKEND
    here, leave_home = HOME, day + timedelta(hours=7)
    moment = leave_home
    for place, hour in stops:
        leave = day + timedelta(hours=hour, minutes=plan.rng.randint(-20, 10))
        plan.stay(here, moment, max(leave, moment))
        moment = plan.travel(here, place, max(leave, moment))
        here = place
    # Half of evenings end with a drink. Home comes last either way.
    if plan.rng.random() < 0.5:
        leave = moment + timedelta(minutes=plan.rng.randint(70, 100))
        plan.stay(here, moment, leave)
        moment = plan.travel(here, BAR, leave)
        here = BAR
    leave = moment + timedelta(minutes=plan.rng.randint(60, 110))
    plan.stay(here, moment, leave)
    moment = plan.travel(here, HOME, leave)
    plan.stay(HOME, moment, moment + timedelta(minutes=40))
    return plan.events


def _events(now: datetime) -> Iterator[Event]:
    today = datetime.combine(now.date(), time.min)
    for days_ago in range(DAYS_BACK, -1, -1):
        for event in _day_events(today - timedelta(days=days_ago)):
            if event.ts <= now.timestamp():
                yield event


def demo_week_collector(now: Callable[[], datetime] = datetime.now) -> Collector:
    return Collector(
        name="demo_week",
        source="demo",
        collect=lambda cursor: full_scan("demo_week", _events(now())),
    )
