import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { Icon } from "./icons";
import { eventText, fixesUpTo, formatClock, hourOf, kmUpTo, nearestEvent, type Track } from "./track";
import type { Day, HistoryEvent } from "./types";

const TICK_PITCH_PX = 3;
const TICK_WIDTH_PX = 2;
const CURRENT_EVENT_WINDOW_S = 10 * 60;
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
  onDate: (date: string) => void;
  onSeek: (t: number) => void;
  onTogglePlay: () => void;
};

/** Activity along the day, drawn as ticks that are brighter behind the playhead. */
function Ticks({ events, start, end, progress }: {
  events: HistoryEvent[];
  start: number;
  end: number;
  progress: number;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const element = canvas.current as HTMLCanvasElement;
    const observer = new ResizeObserver(() => setWidth(element.clientWidth));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const bins = useMemo(() => {
    const counts = new Array<number>(Math.max(1, Math.floor(width / TICK_PITCH_PX))).fill(0);
    for (const event of events) {
      const share = (event.ts - start) / (end - start);
      const bin = Math.min(counts.length - 1, Math.floor(share * counts.length));
      if (bin >= 0) counts[bin] += 1;
    }
    return counts;
  }, [events, start, end, width]);

  useEffect(() => {
    const element = canvas.current as HTMLCanvasElement;
    const context = element.getContext("2d");
    if (!context || width === 0) return;
    const height = element.clientHeight;
    const ratio = window.devicePixelRatio || 1;
    element.width = width * ratio;
    element.height = height * ratio;
    context.scale(ratio, ratio);
    const peak = Math.max(1, ...bins);
    bins.forEach((count, i) => {
      if (count === 0) return;
      const barHeight = height * (0.4 + 0.6 * Math.sqrt(count / peak));
      const played = (i + 0.5) / bins.length <= progress;
      context.fillStyle = played ? "#7dd3fc" : "rgba(125, 211, 252, 0.32)";
      context.beginPath();
      context.roundRect(i * TICK_PITCH_PX, (height - barHeight) / 2, TICK_WIDTH_PX, barHeight, 1);
      context.fill();
    });
  }, [bins, progress, width]);

  return <canvas ref={canvas} className="ticks" aria-hidden="true" />;
}

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
  onDate,
  onSeek,
  onTogglePlay,
}: Props) {
  const rail = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ t: number; share: number } | null>(null);
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

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const moment = momentAt(event.clientX);
    setHover(moment);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) onSeek(moment.t);
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
  const current = nearestEvent(events, t, CURRENT_EVENT_WINDOW_S);
  const hovered = hover && nearestEvent(events, hover.t, CURRENT_EVENT_WINDOW_S);
  const km = kmUpTo(track, t);

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
        onPointerLeave={() => setHover(null)}
        onKeyDown={onKeyDown}
      >
        <Ticks events={events} start={start} end={end} progress={progress} />
        <div className="thumb" style={{ left: `${progress * 100}%` }} />
        {hover && (
          <div className="rail-tip" style={{ left: `${hover.share * 100}%` }}>
            <span className="rail-tip-time">{formatClock(hover.t, end).slice(0, 5)}</span>
            {hovered && <span className="rail-tip-text">{eventText(hovered)}</span>}
          </div>
        )}
      </div>

      <footer className="scrubber-bottom">
        <span className="stat">
          <Icon name="pin" />
          <strong>{fixesUpTo(track, t)}</strong> pts
        </span>
        <span className="now" title={current ? eventText(current) : undefined}>
          {loading ? (
            "Loading…"
          ) : current ? (
            <>
              <span className="now-source">{current.source}</span> {eventText(current)}
            </>
          ) : events.length === 0 ? (
            "Nothing recorded this day"
          ) : null}
        </span>
        <span className="stat">
          <Icon name="route" />
          <strong>{km < 10 ? km.toFixed(1) : Math.round(km)}</strong> km
        </span>
      </footer>
    </section>
  );
}
