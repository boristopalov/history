import { memo, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { Icon } from "./icons";
import {
  eventsInRange,
  fixesUpTo,
  formatClock,
  formatRange,
  hourOf,
  kmUpTo,
  RANGES_S,
  type Track,
} from "./track";
import type { Day, HistoryEvent } from "./types";

const TICK_PITCH_PX = 3;
const TICK_WIDTH_PX = 2;
const TICK_PLAYED = "#7dd3fc";
const TICK_AHEAD = "rgba(125, 211, 252, 0.32)";
const AXIS_HOURS = [0, 6, 12, 18, 24];

type Props = {
  date: string;
  days: Day[];
  start: number;
  end: number;
  t: number;
  playing: boolean;
  loading: boolean;
  track: Track;
  events: HistoryEvent[];
  groupSize: number;
  rangeS: number;
  eventsOpen: boolean;
  onRange: (rangeS: number) => void;
  onToggleEvents: () => void;
  onDate: (date: string) => void;
  onSeek: (t: number) => void;
  onTogglePlay: () => void;
};

/**
 * Activity along the day, drawn once per day. The timeline stacks a dim copy and a bright copy
 * and clips the bright one at the playhead, so playback never has to redraw this.
 */
const Ticks = memo(function Ticks({ events, start, end, color }: {
  events: HistoryEvent[];
  start: number;
  end: number;
  color: string;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const element = canvas.current as HTMLCanvasElement;
    const observer = new ResizeObserver(() => setWidth(element.clientWidth));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const element = canvas.current as HTMLCanvasElement;
    const context = element.getContext("2d");
    if (!context || width === 0) return;

    const bins = new Array<number>(Math.max(1, Math.floor(width / TICK_PITCH_PX))).fill(0);
    for (const event of events) {
      const share = (event.ts - start) / (end - start);
      const bin = Math.min(bins.length - 1, Math.floor(share * bins.length));
      if (bin >= 0) bins[bin] += 1;
    }

    const height = element.clientHeight;
    const ratio = window.devicePixelRatio || 1;
    element.width = width * ratio;
    element.height = height * ratio;
    context.scale(ratio, ratio);
    context.fillStyle = color;
    const peak = Math.max(1, ...bins);
    bins.forEach((count, i) => {
      if (count === 0) return;
      const barHeight = height * (0.4 + 0.6 * Math.sqrt(count / peak));
      context.beginPath();
      context.roundRect(i * TICK_PITCH_PX, (height - barHeight) / 2, TICK_WIDTH_PX, barHeight, 1);
      context.fill();
    });
  }, [events, start, end, color, width]);

  return <canvas ref={canvas} className="ticks" aria-hidden="true" />;
});

export function Scrubber({
  date,
  days,
  start,
  end,
  t,
  playing,
  loading,
  track,
  events,
  groupSize,
  rangeS,
  eventsOpen,
  onRange,
  onToggleEvents,
  onDate,
  onSeek,
  onTogglePlay,
}: Props) {
  const rail = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ t: number; share: number } | null>(null);
  const latestMove = useRef<{ moment: { t: number; share: number }; dragging: boolean } | null>(
    null,
  );
  const moveFrame = useRef<number | null>(null);
  const progress = Math.min(1, Math.max(0, (t - start) / (end - start)));

  const momentAt = (clientX: number) => {
    const box = (rail.current as HTMLDivElement).getBoundingClientRect();
    const share = Math.min(1, Math.max(0, (clientX - box.left) / box.width));
    return { share, t: start + share * (end - start) };
  };

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    onSeek(momentAt(event.clientX).t);
  };

  // A mouse can report far more often than the screen draws, so moves wait for the next frame
  // and only the latest one counts.
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const dragging = event.currentTarget.hasPointerCapture(event.pointerId);
    latestMove.current = { moment: momentAt(event.clientX), dragging };
    if (moveFrame.current !== null) return;
    moveFrame.current = requestAnimationFrame(() => {
      moveFrame.current = null;
      const move = latestMove.current;
      if (!move) return;
      setHover(move.moment);
      if (move.dragging) onSeek(move.moment.t);
    });
  };

  const onPointerLeave = () => {
    latestMove.current = null;
    setHover(null);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 3600 : 300;
    const target = {
      ArrowLeft: t - step,
      ArrowRight: t + step,
      Home: start,
      End: end,
    }[event.key];
    if (target === undefined) return;
    event.preventDefault();
    onSeek(Math.min(end, Math.max(start, target)));
  };

  const earlier = days.filter((day) => day.date < date).at(-1);
  const later = days.find((day) => day.date > date);
  const hoveredCount = hover ? eventsInRange(events, hover.t, rangeS).length : 0;
  const km = kmUpTo(track, t);
  const bandFrom = Math.max(0, (t - rangeS - start) / (end - start));
  const bandTo = Math.min(1, (t + rangeS - start) / (end - start));

  return (
    <section className="scrubber surface" aria-label="Timeline">
      <header className="scrubber-top">
        <div className="date-picker">
          <button
            className="ghost"
            disabled={!earlier}
            aria-label="Previous day with data"
            onClick={() => earlier && onDate(earlier.date)}
          >
            <Icon name="left" />
          </button>
          <input
            type="date"
            aria-label="Date"
            value={date}
            onChange={(event) => event.target.value && onDate(event.target.value)}
          />
          <button
            className="ghost"
            disabled={!later}
            aria-label="Next day with data"
            onClick={() => later && onDate(later.date)}
          >
            <Icon name="right" />
          </button>
        </div>
        <div className="transport">
          <button
            className="primary"
            aria-label={playing ? "Pause" : "Play"}
            onClick={onTogglePlay}
            disabled={events.length === 0}
          >
            <Icon name={playing ? "pause" : "play"} />
            <span className="play-label">{playing ? "Pause" : "Play"}</span>
          </button>
          <output className="clock" aria-label="Time">
            {formatClock(t, end)}
          </output>
        </div>
      </header>

      <div className="axis" aria-hidden="true">
        {AXIS_HOURS.map((hour) => {
          const at = hour === 24 ? end : hourOf(date, hour);
          return (
            <span key={hour} style={{ left: `${((at - start) / (end - start)) * 100}%` }}>
              {String(hour).padStart(2, "0")}:00
            </span>
          );
        })}
      </div>

      <div
        ref={rail}
        className="rail"
        role="slider"
        tabIndex={0}
        aria-label="Time of day"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(progress * 100)}
        aria-valuetext={formatClock(t, end)}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerLeave={onPointerLeave}
        onKeyDown={onKeyDown}
      >
        <Ticks events={events} start={start} end={end} color={TICK_AHEAD} />
        <div className="ticks-played" style={{ clipPath: `inset(0 ${(1 - progress) * 100}% 0 0)` }}>
          <Ticks events={events} start={start} end={end} color={TICK_PLAYED} />
        </div>
        <div
          className="band"
          style={{ left: `${bandFrom * 100}%`, width: `${(bandTo - bandFrom) * 100}%` }}
        />
        <div className="thumb" style={{ left: `${progress * 100}%` }} />
        {hover && (
          <div className="rail-tip" style={{ left: `${hover.share * 100}%` }}>
            <span className="rail-tip-time">{formatClock(hover.t, end).slice(0, 5)}</span>
            {hoveredCount > 0 && (
              <span>
                {hoveredCount} {hoveredCount === 1 ? "event" : "events"}
              </span>
            )}
          </div>
        )}
      </div>

      <footer className="scrubber-bottom">
        <span className="stat">
          <Icon name="pin" />
          <strong>{fixesUpTo(track, t)}</strong> pts
        </span>
        <span className="group-controls">
          {loading ? (
            "Loading…"
          ) : events.length === 0 ? (
            "Nothing recorded this day"
          ) : (
            <>
              <button
                className="group-count"
                aria-expanded={eventsOpen}
                aria-label={`${eventsOpen ? "Hide" : "Show"} ${groupSize} events`}
                title={eventsOpen ? "Hide events" : "Show events"}
                onClick={onToggleEvents}
              >
                <strong>{groupSize}</strong> {groupSize === 1 ? "event" : "events"}
                <Icon name="panel" />
              </button>
              <select
                aria-label="Show events within"
                value={rangeS}
                onChange={(event) => onRange(Number(event.target.value))}
              >
                {RANGES_S.map((option) => (
                  <option key={option} value={option}>
                    {formatRange(option)}
                  </option>
                ))}
              </select>
            </>
          )}
        </span>
        <span className="stat">
          <Icon name="route" />
          <strong>{km < 10 ? km.toFixed(1) : Math.round(km)}</strong> km
        </span>
      </footer>
    </section>
  );
}
