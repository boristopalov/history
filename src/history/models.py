"""The wire format shared by the daemon and the server."""

from typing import Any, Self

from pydantic import BaseModel, Field, model_validator


class Event(BaseModel):
    """One thing that happened. Every data source is normalised to this shape."""

    source: str = Field(min_length=1)  # category, e.g. "messages", "photos", "location"
    # Stable within `source`; re-sending the same id updates the event.
    source_id: str = Field(min_length=1)
    ts: float  # unix seconds, UTC
    end_ts: float | None = None
    title: str | None = None
    body: str | None = None
    url: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    # True means "I was physically at lat/lon at ts", so other events can be located
    # from this one. A calendar event has a place but doesn't prove you went.
    is_fix: bool = False
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _coordinates_are_complete(self) -> Self:
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon must be set together")
        if self.is_fix and self.lat is None:
            raise ValueError("is_fix requires lat and lon")
        return self


class Batch(BaseModel):
    """Events from one collector. The cursor is committed with them, atomically."""

    collector: str = Field(min_length=1)  # unique name; the cursor is stored under it
    cursor: str | None = None  # None leaves the stored cursor untouched
    events: list[Event]
