import { memo, useEffect, useRef, useState } from "react";
import { Icon, type IconName } from "./icons";
import { eventLines, formatClock, sourceKind } from "./track";
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

// A wide range can hold hundreds of events and the list changes on every frame of playback,
// so only the rows in view exist. Rows are one fixed height, which keeps that to arithmetic.
const ROW_PX = 44; // matches .event-row
const ROWS_IN_VIEW = 8; // the card's tallest list, rounded up
const EXTRA_ROWS = 3;

const SOURCES: Record<string, { icon: IconName; label: string }> = {
  app_usage: { icon: "app", label: "App" },
  browser: { icon: "globe", label: "Browsing" },
  calendar: { icon: "calendar", label: "Calendar" },
  events: { icon: "ticket", label: "Invite" },
  git: { icon: "commit", label: "Commit" },
  health: { icon: "heart", label: "Health" },
  messages: { icon: "message", label: "Message" },
  music: { icon: "music", label: "Music" },
  notes: { icon: "note", label: "Note" },
  photos: { icon: "photo", label: "Photo" },
  receipts: { icon: "receipt", label: "Receipt" },
  transactions: { icon: "card", label: "Purchase" },
};

function timeLabel(event: HistoryEvent, dayEnd: number): string {
  const from = formatClock(event.ts, dayEnd).slice(0, 5);
  if (!event.end_ts || event.end_ts - event.ts < MIN_DURATION_S) return from;
  return `${from}–${formatClock(event.end_ts, dayEnd).slice(0, 5)}`;
}

/** Only rows whose state changed rerender, which keeps playback smooth on a busy day. */
const EventRow = memo(function EventRow({ event, index, total, dayEnd, ahead, closest, onPick }: {
  event: HistoryEvent;
  index: number;
  total: number;
  dayEnd: number;
  ahead: boolean;
  closest: boolean;
  onPick: (event: HistoryEvent) => void;
}) {
  const classes = ["event-row", ahead && "ahead", closest && "closest"].filter(Boolean);
  // A source nobody has given an icon, like a plugin's, still gets a row.
  const { icon, label } = SOURCES[sourceKind(event.source)] ?? {
    icon: "dot",
    label: event.source,
  };
  const [primary, secondary] = eventLines(event, label);
  return (
    <li style={{ top: index * ROW_PX }} aria-posinset={index + 1} aria-setsize={total}>
      <button className={classes.join(" ")} onClick={() => onPick(event)}>
        <span className="event-icon" title={label}>
          <Icon name={icon} />
        </span>
        <span className="event-body">
          <span className="event-primary" title={primary}>
            {primary}
          </span>
          <span className="event-secondary" title={secondary}>
            {secondary}
          </span>
        </span>
        <span className="event-time">{timeLabel(event, dayEnd)}</span>
      </button>
    </li>
  );
});

/** By start time, so that a long event doesn't hold the highlight for as long as it runs. */
function closestIndex(group: HistoryEvent[], t: number): number {
  let best = -1;
  group.forEach((event, i) => {
    if (best < 0 || Math.abs(event.ts - t) < Math.abs(group[best].ts - t)) best = i;
  });
  return best;
}

export function EventCard({ group, t, start, end, rangeS, onPick, onClose }: Props) {
  const list = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const closest = closestIndex(group, t);
  const from = formatClock(Math.max(start, t - rangeS), end).slice(0, 5);
  const to = formatClock(Math.min(end, t + rangeS), end).slice(0, 5);

  // Keep the row nearest the playhead in view.
  useEffect(() => {
    const element = list.current;
    if (!element || closest < 0) return;
    const top = closest * ROW_PX;
    if (top < element.scrollTop) element.scrollTop = top;
    else if (top + ROW_PX > element.scrollTop + element.clientHeight) {
      element.scrollTop = top + ROW_PX - element.clientHeight;
    }
  }, [closest]);

  const lastStart = Math.max(0, group.length - ROWS_IN_VIEW);
  const firstRow = Math.max(0, Math.min(Math.floor(scrollTop / ROW_PX), lastStart) - EXTRA_ROWS);
  const rows = group.slice(firstRow, firstRow + ROWS_IN_VIEW + EXTRA_ROWS * 2);

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
        <div
          className="event-scroll"
          ref={list}
          onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
        >
          <ol className="event-list" style={{ height: group.length * ROW_PX }}>
            {rows.map((event, i) => (
              <EventRow
                key={`${event.source}/${event.source_id}`}
                event={event}
                index={firstRow + i}
                total={group.length}
                dayEnd={end}
                ahead={event.ts > t}
                closest={firstRow + i === closest}
                onPick={onPick}
              />
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
