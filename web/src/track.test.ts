import { describe, expect, it } from "vitest";
import {
  buildTrack,
  dayBounds,
  eventText,
  fixesUpTo,
  formatClock,
  hourOf,
  kmUpTo,
  localDate,
  MAX_GAP_S,
  nearestEvent,
  positionAt,
} from "./track";
import type { HistoryEvent } from "./types";

function event(ts: number, fields: Partial<HistoryEvent> = {}): HistoryEvent {
  return {
    source: "messages",
    source_id: String(ts),
    ts,
    end_ts: null,
    title: null,
    body: null,
    url: null,
    lat: null,
    lon: null,
    is_fix: false,
    location: null,
    ...fields,
  };
}

function fix(ts: number, lat: number, lon: number): HistoryEvent {
  return event(ts, { source: "location", lat, lon, is_fix: true });
}

describe("buildTrack", () => {
  it("keeps only fixes, oldest first", () => {
    const planned = event(50, { source: "calendar", lat: 1, lon: 1 });
    const track = buildTrack([fix(200, 2, 2), planned, event(150), fix(100, 1, 1)]);
    expect(track.fixes.map((f) => f.t)).toEqual([100, 200]);
  });

  it("adds up distance between close fixes", () => {
    const track = buildTrack([fix(0, 0, 0), fix(60, 0, 1), fix(120, 0, 2)]);
    expect(kmUpTo(track, 60)).toBeCloseTo(111.19, 1);
    expect(kmUpTo(track, 120)).toBeCloseTo(222.39, 1);
  });

  it("does not count a jump across a long gap as distance covered", () => {
    const track = buildTrack([fix(0, 0, 0), fix(MAX_GAP_S + 1, 0, 1)]);
    expect(kmUpTo(track, MAX_GAP_S + 1)).toBe(0);
  });
});

describe("fixesUpTo", () => {
  it("counts fixes at or before a moment", () => {
    const track = buildTrack([fix(100, 0, 0), fix(200, 0, 0), fix(300, 0, 0)]);
    expect([50, 100, 250, 300, 400].map((t) => fixesUpTo(track, t))).toEqual([0, 1, 2, 3, 3]);
  });
});

describe("positionAt", () => {
  it("has nothing to say before the first fix", () => {
    expect(positionAt(buildTrack([fix(100, 1, 1)]), 99)).toBeNull();
    expect(positionAt(buildTrack([]), 100)).toBeNull();
  });

  it("moves in a straight line between close fixes", () => {
    const position = positionAt(buildTrack([fix(0, 0, 0), fix(100, 10, 20)]), 25);
    expect(position).toEqual({ lat: 2.5, lon: 5, stale: false });
  });

  it("stays put across a long gap and goes stale once the fix is old", () => {
    const track = buildTrack([fix(0, 1, 1), fix(5 * MAX_GAP_S, 9, 9)]);
    expect(positionAt(track, MAX_GAP_S - 1)).toEqual({ lat: 1, lon: 1, stale: false });
    expect(positionAt(track, MAX_GAP_S + 1)).toEqual({ lat: 1, lon: 1, stale: true });
  });

  it("goes stale after the last fix of the day", () => {
    const track = buildTrack([fix(0, 1, 1)]);
    expect(positionAt(track, 10)?.stale).toBe(false);
    expect(positionAt(track, MAX_GAP_S + 1)?.stale).toBe(true);
  });
});

describe("nearestEvent", () => {
  it("picks the closest event within range and ignores fixes", () => {
    const events = [event(100), fix(205, 0, 0), event(190), event(400)];
    expect(nearestEvent(events, 205, 60)?.ts).toBe(190);
    expect(nearestEvent(events, 300, 60)).toBeNull();
  });
});

describe("eventText", () => {
  it("uses whichever text the event has", () => {
    expect(eventText(event(0, { title: "Priya", body: "dinner?" }))).toBe("Priya: dinner?");
    expect(eventText(event(0, { title: "Night Bus" }))).toBe("Night Bus");
    expect(eventText(event(0, { url: "https://example.com" }))).toBe("https://example.com");
    expect(eventText(event(0))).toBe("messages");
  });
});

describe("calendar days", () => {
  it("round-trips between a date and its bounds", () => {
    const [start, end] = dayBounds("2026-11-05");
    expect(localDate(start)).toBe("2026-11-05");
    expect(localDate(end - 1)).toBe("2026-11-05");
    expect(localDate(end)).toBe("2026-11-06");
  });

  it("gets the hours of a day right", () => {
    const [start] = dayBounds("2026-06-15");
    expect(hourOf("2026-06-15", 0)).toBe(start);
    expect(formatClock(hourOf("2026-06-15", 6), Infinity)).toBe("06:00:00");
  });

  it("ends the clock at 24:00:00", () => {
    const [start, end] = dayBounds("2026-11-05");
    expect(formatClock(end, end)).toBe("24:00:00");
    expect(formatClock(start, end)).toBe("00:00:00");
  });
});
