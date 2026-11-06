/** The day's path, and what it says about any moment. Pure, so it can be tested alone. */

import type { HistoryEvent } from "./types";

export type Fix = { t: number; lat: number; lon: number };

export type Track = {
  fixes: Fix[]; // oldest first
  km: number[]; // km[i] is the distance covered up to and including fixes[i]
};

export type Position = {
  lat: number;
  lon: number;
  /** True when the last fix is too old to say you were still there. */
  stale: boolean;
};

/** Beyond this, the time between two fixes says nothing about the route between them. */
export const MAX_GAP_S = 30 * 60;

const EARTH_RADIUS_KM = 6371;

function haversineKm(a: Fix, b: Fix): number {
  const radians = (degrees: number) => (degrees * Math.PI) / 180;
  const dLat = radians(b.lat - a.lat);
  const dLon = radians(b.lon - a.lon);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(radians(a.lat)) * Math.cos(radians(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(h));
}

export function buildTrack(events: HistoryEvent[]): Track {
  const fixes = events
    .filter((e) => e.is_fix && e.lat !== null && e.lon !== null)
    .map((e) => ({ t: e.ts, lat: e.lat as number, lon: e.lon as number }))
    .sort((a, b) => a.t - b.t);
  const km: number[] = [];
  fixes.forEach((fix, i) => {
    // A jump across a long gap isn't a distance you're known to have walked.
    const covered = i > 0 && fix.t - fixes[i - 1].t <= MAX_GAP_S;
    km.push((km[i - 1] ?? 0) + (covered ? haversineKm(fixes[i - 1], fix) : 0));
  });
  return { fixes, km };
}

/** How many fixes happened at or before t. */
export function fixesUpTo(track: Track, t: number): number {
  let low = 0;
  let high = track.fixes.length;
  while (low < high) {
    const middle = (low + high) >> 1;
    if (track.fixes[middle].t <= t) low = middle + 1;
    else high = middle;
  }
  return low;
}

export function kmUpTo(track: Track, t: number): number {
  const count = fixesUpTo(track, t);
  return count === 0 ? 0 : track.km[count - 1];
}

/**
 * Where you were at t. Between two close fixes that's a straight line. Across a long gap
 * you stay at the last fix and it's marked stale, rather than gliding along a route
 * nothing supports. Before the first fix of the day there's nothing to show.
 */
export function positionAt(track: Track, t: number): Position | null {
  const count = fixesUpTo(track, t);
  if (count === 0) return null;
  const before = track.fixes[count - 1];
  const after = track.fixes[count];
  if (after && after.t - before.t <= MAX_GAP_S) {
    const share = (t - before.t) / (after.t - before.t);
    return {
      lat: before.lat + (after.lat - before.lat) * share,
      lon: before.lon + (after.lon - before.lon) * share,
      stale: false,
    };
  }
  return { lat: before.lat, lon: before.lon, stale: t - before.t > MAX_GAP_S };
}

/** The event closest to t, among those within `withinS`. Fixes are the path, not events. */
export function nearestEvent(
  events: HistoryEvent[],
  t: number,
  withinS: number,
): HistoryEvent | null {
  let best: HistoryEvent | null = null;
  for (const event of events) {
    if (event.is_fix) continue;
    const distance = Math.abs(event.ts - t);
    if (distance <= withinS && (!best || distance < Math.abs(best.ts - t))) best = event;
  }
  return best;
}

/** Start and end of a local calendar day, in unix seconds. A DST day isn't 24 hours. */
export function dayBounds(date: string): [number, number] {
  const [year, month, day] = date.split("-").map(Number);
  return [
    new Date(year, month - 1, day).getTime() / 1000,
    new Date(year, month - 1, day + 1).getTime() / 1000,
  ];
}

/** The local calendar day of a moment, as YYYY-MM-DD. */
export function localDate(ts: number): string {
  const d = new Date(ts * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Unix seconds of an hour on a local calendar day. */
export function hourOf(date: string, hour: number): number {
  const [year, month, day] = date.split("-").map(Number);
  return new Date(year, month - 1, day, hour).getTime() / 1000;
}

/** A clock on the day's scale, which ends at 24:00:00 rather than wrapping to midnight. */
export function formatClock(t: number, dayEnd: number): string {
  if (t >= dayEnd) return "24:00:00";
  const d = new Date(t * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** One line for an event: "Priya: dinner at 8?", or whichever of those it has. */
export function eventText(event: HistoryEvent): string {
  const text = [event.title, event.body].filter(Boolean).join(": ");
  return text || event.url || event.source;
}
