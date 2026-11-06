import { memo, useEffect, useRef } from "react";
import { Icon } from "./icons";
import { eventText, formatClock } from "./track";
import type { HistoryEvent } from "./types";

type Props = {
  group: HistoryEvent[];
  t: number;
  start: number;
  end: number;
  rangeS: number;
  onPick: (event: HistoryEvent) => void;
  onClose: () => void;
};

const MIN_DURATION_S = 60;

function timeLabel(event: HistoryEvent, dayEnd: number): string {
  const from = formatClock(event.ts, dayEnd).slice(0, 5);
  if (!event.end_ts || event.end_ts - event.ts < MIN_DURATION_S) return from;
  return `${from}–${formatClock(event.end_ts, dayEnd).slice(0, 5)}`;
}

/** Only rows whose state changed rerender, which keeps playback smooth on a busy day. */
const EventRow = memo(function EventRow({ event, dayEnd, ahead, closest, onPick }: {
  event: HistoryEvent;
  dayEnd: number;
  ahead: boolean;
  closest: boolean;
  onPick: (event: HistoryEvent) => void;
}) {
  const classes = ["event-row", ahead && "ahead", closest && "closest"].filter(Boolean);
  return (
    <li>
      <button className={classes.join(" ")} onClick={() => onPick(event)}>
        <span className="event-time">{timeLabel(event, dayEnd)}</span>
        <span className="event-body">
          <span className="event-source">{event.source}</span>
          <span className="event-text" title={eventText(event)}>
            {eventText(event)}
          </span>
        </span>
      </button>
    </li>
  );
});

function closestTo(group: HistoryEvent[], t: number): HistoryEvent | null {
  const distance = (event: HistoryEvent) =>
    t < event.ts ? event.ts - t : Math.max(0, t - (event.end_ts ?? event.ts));
  return group.reduce<HistoryEvent | null>(
    (best, event) => (!best || distance(event) < distance(best) ? event : best),
    null,
  );
}

export function EventCard({ group, t, start, end, rangeS, onPick, onClose }: Props) {
  const list = useRef<HTMLOListElement>(null);
  const closest = closestTo(group, t);
  const from = formatClock(Math.max(start, t - rangeS), end).slice(0, 5);
  const to = formatClock(Math.min(end, t + rangeS), end).slice(0, 5);

  // Keep the row nearest the playhead in view. Scrolling the list itself, rather than
  // scrollIntoView, can't move anything else on the page.
  useEffect(() => {
    const element = list.current;
    const row = element?.querySelector<HTMLElement>(".closest");
    if (!element || !row) return;
    const top = row.offsetTop - element.offsetTop;
    if (top < element.scrollTop) element.scrollTop = top;
    else if (top + row.offsetHeight > element.scrollTop + element.clientHeight) {
      element.scrollTop = top + row.offsetHeight - element.clientHeight;
    }
  }, [closest]);

  return (
    <section className="event-card surface" aria-label="Events around this time">
      <header className="event-card-top">
        <span>
          <strong>{group.length}</strong> {group.length === 1 ? "event" : "events"}
        </span>
        <span className="event-card-range">
          {from}–{to}
        </span>
        <button className="ghost" aria-label="Close events" onClick={onClose}>
          <Icon name="close" />
        </button>
      </header>
      {group.length === 0 ? (
        <p className="event-empty">Nothing in this range.</p>
      ) : (
        <ol className="event-list" ref={list}>
          {group.map((event) => (
            <EventRow
              key={`${event.source}/${event.source_id}`}
              event={event}
              dayEnd={end}
              ahead={event.ts > t}
              closest={event === closest}
              onPick={onPick}
            />
          ))}
        </ol>
      )}
    </section>
  );
}
