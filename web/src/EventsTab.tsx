import { memo } from "react";
import { Row, RowList } from "./Rows";
import { sourceInfo } from "./sources";
import { eventLines, formatClock } from "./track";
import type { HistoryEvent } from "./types";

type Props = {
  group: HistoryEvent[];
  dayEmpty: boolean;
  t: number;
  start: number;
  end: number;
  rangeS: number;
  onPick: (event: HistoryEvent) => void;
};

const MIN_DURATION_S = 60;

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
  const [primary, secondary] = eventLines(event, sourceInfo(event.source).label);
  return (
    <Row
      index={index}
      total={total}
      source={event.source}
      primary={primary}
      secondary={secondary}
      time={timeLabel(event, dayEnd)}
      ahead={ahead}
      active={closest}
      onClick={() => onPick(event)}
    />
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

export function EventsTab({ group, dayEmpty, t, start, end, rangeS, onPick }: Props) {
  const closest = closestIndex(group, t);
  const from = formatClock(Math.max(start, t - rangeS), end).slice(0, 5);
  const to = formatClock(Math.min(end, t + rangeS), end).slice(0, 5);

  return (
    <section className="tab events-tab" aria-label="Events around this time">
      <header className="events-top">
        <span>
          <strong>{group.length}</strong> {group.length === 1 ? "event" : "events"}
        </span>
        <span className="events-range">
          {from}–{to}
        </span>
      </header>
      {group.length === 0 ? (
        <p className="event-empty">
          {dayEmpty ? "Nothing recorded this day." : "Nothing in this range."}
        </p>
      ) : (
        <RowList
          items={group}
          follow={closest}
          renderRow={(event, index) => (
            <EventRow
              key={`${event.source}/${event.source_id}`}
              event={event}
              index={index}
              total={group.length}
              dayEnd={end}
              ahead={event.ts > t}
              closest={index === closest}
              onPick={onPick}
            />
          )}
        />
      )}
    </section>
  );
}
