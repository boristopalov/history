import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchDays, fetchEvents } from "./api";
import { CalendarView } from "./CalendarView";
import { EventCard } from "./EventCard";
import { MapView, type Camera, type Pin, type Point } from "./MapView";
import { Panel } from "./Panel";
import { Scrubber } from "./Scrubber";
import {
  buildTrack,
  dayBounds,
  DEFAULT_RANGE_S,
  eventsInRange,
  localDate,
  RANGES_S,
} from "./track";
import type { Anchor, Day, HistoryEvent, QueryResult } from "./types";

const PLAYBACK_SPEED = 1800; // seconds of the day per second: a day plays in 48 seconds
const PANEL_WIDTH_PX = 400;
const CARD_WIDTH_PX = 340;
const RANGE_KEY = "history.eventRange";
const NARROW_PX = 820;

const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;

/** The most recent day worth opening on. The log also holds calendar events in the future. */
function latestDay(days: Day[]): string {
  const today = localDate(Date.now() / 1000);
  const past = days.filter((day) => day.date <= today);
  return past.filter((day) => day.fixes > 0).at(-1)?.date ?? past.at(-1)?.date ?? today;
}

function savedRange(): number {
  try {
    const saved = Number(localStorage.getItem(RANGE_KEY));
    return RANGES_S.includes(saved) ? saved : DEFAULT_RANGE_S;
  } catch {
    return DEFAULT_RANGE_S;
  }
}

function eventPoints(events: HistoryEvent[]): Point[] {
  const fixes = events.filter((event) => event.is_fix);
  return (fixes.length > 0 ? fixes : events).flatMap((event) =>
    event.location ? [event.location] : [],
  );
}

export function App() {
  const [days, setDays] = useState<Day[]>([]);
  const [date, setDate] = useState<string | null>(null);
  const [events, setEvents] = useState<HistoryEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [pins, setPins] = useState<Pin[]>([]);
  const [camera, setCamera] = useState<Camera | null>(null);
  const [panelOpen, setPanelOpen] = useState(() => window.innerWidth > NARROW_PX);
  const [narrow, setNarrow] = useState(() => window.innerWidth <= NARROW_PX);
  const [cardOpen, setCardOpen] = useState(() => window.innerWidth > NARROW_PX);
  const [rangeS, setRangeS] = useState(savedRange);

  // A jump to another day sets where to land before that day has loaded.
  const landing = useRef<{ t: number; point: Point | null } | null>(null);

  const [start, end] = useMemo(
    () => dayBounds(date ?? localDate(Date.now() / 1000)),
    [date],
  );
  const track = useMemo(() => buildTrack(events), [events]);
  const group = useMemo(() => eventsInRange(events, t, rangeS), [events, t, rangeS]);

  useEffect(() => {
    const onResize = () => setNarrow(window.innerWidth <= NARROW_PX);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    fetchDays(tz)
      .then((all) => {
        setDays(all);
        setDate((current) => current ?? latestDay(all));
      })
      .catch(() => {
        setFailure("Can't reach the history server.");
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!date) return;
    const controller = new AbortController();
    setLoading(true);
    setPlaying(false);
    fetchEvents(start, end, controller.signal)
      .then((loaded) => {
        const jump = landing.current;
        landing.current = null;
        setEvents(loaded);
        setFailure(null);
        setLoading(false);
        setT(jump ? jump.t : Math.min(end, Math.max(start, Date.now() / 1000)));
        setCamera({ points: jump?.point ? [jump.point] : eventPoints(loaded) });
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        landing.current = null;
        setFailure("Couldn't load this day.");
        setLoading(false);
      });
    return () => controller.abort();
  }, [date, start, end]);

  // Playback. tRef lets the frame loop advance from the latest time without rerunning.
  const tRef = useRef(t);
  tRef.current = t;
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last = performance.now();
    const step = (now: number) => {
      const next = tRef.current + ((now - last) / 1000) * PLAYBACK_SPEED;
      last = now;
      if (next >= end) {
        setT(end);
        setPlaying(false);
        return;
      }
      setT(next);
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [playing, end]);

  const seek = useCallback((target: number) => {
    setPlaying(false);
    setT(target);
  }, []);

  const togglePlay = useCallback(() => {
    if (!playing && tRef.current >= end - 60) {
      // From the end, start again at the day's first event rather than at empty midnight.
      const first = events.reduce((earliest, event) => Math.min(earliest, event.ts), end);
      setT(first < end ? first : start);
    }
    setPlaying(!playing);
  }, [playing, events, start, end]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      const typing = ["INPUT", "TEXTAREA", "BUTTON", "SELECT"].includes(target.tagName);
      if (event.code === "Space" && !typing) {
        event.preventDefault();
        togglePlay();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [togglePlay]);

  const showResult = useCallback((result: QueryResult | null) => {
    const located = (result?.anchors ?? []).flatMap((anchor) =>
      anchor?.location ? [{ ...anchor.location, ts: anchor.ts }] : [],
    );
    setPins(located);
    if (located.length > 0) setCamera({ points: located });
  }, []);

  const jumpTo = useCallback(
    (anchor: NonNullable<Anchor>) => {
      const point = anchor.location;
      if (anchor.ts === null) {
        if (point) setCamera({ points: [point] });
        return;
      }
      setPlaying(false);
      const day = localDate(anchor.ts);
      if (day === date) {
        setT(anchor.ts);
        if (point) setCamera({ points: [point] });
      } else {
        landing.current = { t: anchor.ts, point };
        setDate(day);
      }
    },
    [date],
  );

  const pickEvent = useCallback(
    (event: HistoryEvent) => jumpTo({ ts: event.ts, location: event.location }),
    [jumpTo],
  );

  const changeRange = useCallback((next: number) => {
    setRangeS(next);
    try {
      localStorage.setItem(RANGE_KEY, String(next));
    } catch {
      // Not remembered, but it still applies for this visit.
    }
  }, []);

  // On a phone there's only room for one of these at a time.
  const togglePanel = useCallback(() => {
    if (narrow && !panelOpen) setCardOpen(false);
    setPanelOpen(!panelOpen);
  }, [narrow, panelOpen]);

  const toggleCard = useCallback(() => {
    if (narrow && !cardOpen) setPanelOpen(false);
    setCardOpen(!cardOpen);
  }, [narrow, cardOpen]);

  const pickDate = useCallback((day: string) => {
    landing.current = null;
    setDate(day);
  }, []);

  const padding = useMemo(
    () => ({
      top: 56,
      left: cardOpen && !narrow ? CARD_WIDTH_PX + 56 : 56,
      bottom: 216,
      right: panelOpen && !narrow ? PANEL_WIDTH_PX + 56 : 56,
    }),
    [panelOpen, cardOpen, narrow],
  );

  const noData = !loading && !failure && days.length === 0;

  return (
    <main className="app">
      <MapView
        track={track}
        events={events}
        pins={pins}
        t={t}
        rangeS={rangeS}
        playing={playing}
        camera={camera}
        padding={padding}
        onSeek={seek}
        onPickPin={(pin) =>
          jumpTo({ ts: pin.ts, location: { ...pin, via: "row", gap_s: 0 } })
        }
      />
      {(failure || noData) && (
        <div className="notice surface" role="status">
          {failure ?? "Nothing here yet. Start the daemon with: uv run hist daemon"}
        </div>
      )}
      <Panel
        open={panelOpen}
        tz={tz}
        onToggle={togglePanel}
        onResult={showResult}
        onPick={jumpTo}
      />
      <div className="bottom">
        {date && (
          <div className="dock">
            {cardOpen && events.length > 0 && (
              <EventCard
                group={group}
                t={t}
                start={start}
                end={end}
                rangeS={rangeS}
                onPick={pickEvent}
                onClose={toggleCard}
              />
            )}
            <Scrubber
              date={date}
              days={days}
              start={start}
              end={end}
              t={t}
              playing={playing}
              loading={loading}
              track={track}
              events={events}
              groupSize={group.length}
              rangeS={rangeS}
              cardOpen={cardOpen}
              onRange={changeRange}
              onToggleCard={toggleCard}
              onDate={pickDate}
              onSeek={seek}
              onTogglePlay={togglePlay}
            />
          </div>
        )}
        {days.length > 0 && <CalendarView days={days} selected={date} onPick={pickDate} />}
      </div>
    </main>
  );
}
