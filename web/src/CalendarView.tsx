import {
  memo,
  useCallback,
  useMemo,
  useRef,
  useState,
  type FocusEvent,
  type KeyboardEvent,
  type MouseEvent,
  type PointerEvent,
} from "react";
import { addDays, levelEdges, levelOf, monthLabels, WINDOW_DAYS, yearWeeks } from "./calendar";
import { Icon } from "./icons";
import { localDate } from "./track";
import type { Day } from "./types";

const LEVELS = [1, 2, 3, 4, 5];
const TIP_HALF_WIDTH_PX = 74; // keeps the tooltip inside the card, near its edges
const ARROW_DAYS: Record<string, number> = {
  ArrowUp: -1,
  ArrowDown: 1,
  ArrowLeft: -7,
  ArrowRight: 7,
};

// Building a date format is slow, and a year needs hundreds of labels, so these are shared.
const FULL_DATE = new Intl.DateTimeFormat(undefined, { dateStyle: "full" });
const SHORT_DATE = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
});
const TIP_DATE = new Intl.DateTimeFormat(undefined, {
  weekday: "short",
  month: "short",
  day: "numeric",
  year: "numeric",
});

type Props = {
  days: Day[];
  selected: string | null;
  onPick: (date: string) => void;
};

type Tip = { date: string; x: number; y: number };

function parse(date: string): Date {
  const [year, month, day] = date.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function eventCount(count: number): string {
  return `${count.toLocaleString()} ${count === 1 ? "event" : "events"}`;
}

function dateOf(event: { target: EventTarget }): string | undefined {
  return (event.target as HTMLElement).dataset.date;
}

/**
 * The grid of days. It's separate so that moving a tooltip doesn't rerender a year of cells,
 * and it listens once for all of them rather than once per cell.
 */
const Heatmap = memo(function Heatmap({ weeks, byDate, edges, selected, focusDate, onPick, onHover }: {
  weeks: (string | null)[][];
  byDate: Map<string, Day>;
  edges: number[];
  selected: string | null;
  focusDate: string;
  onPick: (date: string) => void;
  onHover: (date: string | null, cell?: HTMLElement) => void;
}) {
  const grid = useRef<HTMLDivElement>(null);
  const months = useMemo(() => monthLabels(weeks), [weeks]);

  const onClick = (event: MouseEvent) => {
    const date = dateOf(event);
    if (date) onPick(date);
  };

  const onKeyDown = (event: KeyboardEvent) => {
    const date = dateOf(event);
    const step = ARROW_DAYS[event.key];
    if (!date || step === undefined) return;
    event.preventDefault();
    const target = addDays(date, step);
    grid.current?.querySelector<HTMLElement>(`[data-date="${target}"]`)?.focus();
  };

  const show = (event: PointerEvent | FocusEvent) => {
    const date = dateOf(event);
    if (date) onHover(date, event.target as HTMLElement);
    else onHover(null);
  };

  return (
    <div
      ref={grid}
      className="heatmap"
      style={{ gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))` }}
      onClick={onClick}
      onKeyDown={onKeyDown}
      onPointerOver={show}
      onFocus={show}
      onPointerLeave={() => onHover(null)}
      onBlur={() => onHover(null)}
    >
      {months.map(({ week, label }) => (
        <span key={week} className="heatmap-month" style={{ gridColumn: week + 1 }}>
          {label}
        </span>
      ))}
      {weeks.map((week, column) =>
        week.map((date, row) => {
          if (!date) return null;
          const count = byDate.get(date)?.activity ?? 0;
          return (
            <button
              key={date}
              data-date={date}
              data-level={levelOf(count, edges)}
              className={date === selected ? "cell selected" : "cell"}
              style={{ gridColumn: column + 1, gridRow: row + 2 }}
              tabIndex={date === focusDate ? 0 : -1}
              aria-label={`${FULL_DATE.format(parse(date))}: ${eventCount(count)}`}
            />
          );
        }),
      )}
    </div>
  );
});

/**
 * A year of days at a glance, beside the timeline. Picking a day opens it on the map. Memoized,
 * because the app rerenders on every frame of playback and none of that concerns the calendar.
 */
export const CalendarView = memo(function CalendarView({ days, selected, onPick }: Props) {
  const today = localDate(Date.now() / 1000);
  const [end, setEnd] = useState(today);
  const [tip, setTip] = useState<Tip | null>(null);
  const card = useRef<HTMLElement>(null);

  const byDate = useMemo(() => new Map(days.map((day) => [day.date, day])), [days]);
  const weeks = useMemo(() => yearWeeks(end), [end]);
  const first = addDays(end, 1 - WINDOW_DAYS);
  const counts = useMemo(
    () =>
      days
        .filter((day) => day.date >= first && day.date <= end && day.activity > 0)
        .map((day) => day.activity),
    [days, first, end],
  );
  const edges = useMemo(() => levelEdges(counts), [counts]);
  const total = counts.reduce((sum, count) => sum + count, 0);
  const hasEarlier = days.some((day) => day.date < first);
  const focusDate = selected && selected >= first && selected <= end ? selected : end;

  // The card is a positioned ancestor, so the tooltip is placed relative to it.
  const onHover = useCallback((date: string | null, cell?: HTMLElement) => {
    if (!date || !cell) {
      setTip(null);
      return;
    }
    const box = (card.current as HTMLElement).getBoundingClientRect();
    const target = cell.getBoundingClientRect();
    const x = target.left + target.width / 2 - box.left;
    setTip({
      date,
      x: Math.min(box.width - TIP_HALF_WIDTH_PX, Math.max(TIP_HALF_WIDTH_PX, x)),
      y: target.top - box.top,
    });
  }, []);

  return (
    <section ref={card} className="calendar-card surface" aria-label="Year of events">
      <header className="calendar-top">
        <div className="calendar-range">
          <button
            className="ghost"
            aria-label="Previous year"
            disabled={!hasEarlier}
            onClick={() => setEnd(addDays(end, -WINDOW_DAYS))}
          >
            <Icon name="left" />
          </button>
          <h2>
            {SHORT_DATE.format(parse(first))} – {SHORT_DATE.format(parse(end))}
          </h2>
          <button
            className="ghost"
            aria-label="Next year"
            disabled={end >= today}
            onClick={() => {
              const next = addDays(end, WINDOW_DAYS);
              setEnd(next > today ? today : next);
            }}
          >
            <Icon name="right" />
          </button>
        </div>
        {counts.length > 0 ? (
          <span className="legend" aria-label="Events a day, from fewest to most">
            <span>{Math.min(...counts).toLocaleString()}</span>
            {LEVELS.map((level) => (
              <span key={level} className="cell" data-level={level} />
            ))}
            <span>{Math.max(...counts).toLocaleString()}</span>
          </span>
        ) : (
          <span className="calendar-empty">Nothing recorded</span>
        )}
      </header>

      <Heatmap
        weeks={weeks}
        byDate={byDate}
        edges={edges}
        selected={selected}
        focusDate={focusDate}
        onPick={onPick}
        onHover={onHover}
      />

      {tip && (
        <div className="cell-tip" role="status" style={{ left: tip.x, top: tip.y }}>
          <strong>{eventCount(byDate.get(tip.date)?.activity ?? 0)}</strong>
          <span>{TIP_DATE.format(parse(tip.date))}</span>
        </div>
      )}
      {counts.length > 0 && <span className="sr-only">{eventCount(total)} in these 12 months</span>}
    </section>
  );
});
