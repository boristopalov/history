import { useEffect, useRef, useState, type ReactNode } from "react";
import { Icon } from "./icons";
import { sourceInfo } from "./sources";

// A list can hold hundreds of rows and change on every frame of playback, so only the rows in
// view exist. Rows are one fixed height, which keeps that to arithmetic.
const ROW_PX = 44; // matches .event-row
const EXTRA_ROWS = 3;

type RowProps = {
  index: number;
  total: number;
  source: string | null;
  primary: string;
  secondary: string;
  time: string;
  date?: string;
  ahead?: boolean;
  active: boolean;
  onClick: () => void;
};

/** One moment in a list, whether it came from the day's events or from a query. */
export function Row({
  index,
  total,
  source,
  primary,
  secondary,
  time,
  date,
  ahead,
  active,
  onClick,
}: RowProps) {
  const classes = ["event-row", ahead && "ahead", active && "closest"].filter(Boolean);
  const { icon, label } = source ? sourceInfo(source) : { icon: "dot" as const, label: "" };
  return (
    <li style={{ top: index * ROW_PX }} aria-posinset={index + 1} aria-setsize={total}>
      <button className={classes.join(" ")} onClick={onClick}>
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
        <span className="event-time">
          {date && <span>{date}</span>}
          <span>{time}</span>
        </span>
      </button>
    </li>
  );
}

type ListProps<T> = {
  items: T[];
  /** The row to keep in view. */
  follow?: number;
  /** The list goes back to the top when this changes. */
  resetOn?: unknown;
  renderRow: (item: T, index: number) => ReactNode;
};

export function RowList<T>({ items, follow = -1, resetOn, renderRow }: ListProps<T>) {
  const list = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [height, setHeight] = useState(0);

  // Hiding a list resets its scroll without a scroll event, so this reads both.
  useEffect(() => {
    const element = list.current as HTMLDivElement;
    const observer = new ResizeObserver(() => {
      setHeight(element.clientHeight);
      setScrollTop(element.scrollTop);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    (list.current as HTMLDivElement).scrollTop = 0;
  }, [resetOn]);

  useEffect(() => {
    const element = list.current as HTMLDivElement;
    if (follow < 0) return;
    const top = follow * ROW_PX;
    if (top < element.scrollTop) element.scrollTop = top;
    else if (top + ROW_PX > element.scrollTop + element.clientHeight) {
      element.scrollTop = top + ROW_PX - element.clientHeight;
    }
  }, [follow, height]);

  const inView = Math.ceil(height / ROW_PX) + 1;
  const lastStart = Math.max(0, items.length - inView);
  const firstRow = Math.max(0, Math.min(Math.floor(scrollTop / ROW_PX), lastStart) - EXTRA_ROWS);
  const rows = items.slice(firstRow, firstRow + inView + EXTRA_ROWS * 2);

  return (
    <div
      className="event-scroll"
      ref={list}
      onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
    >
      <ol className="event-list" style={{ height: items.length * ROW_PX }}>
        {rows.map((item, i) => renderRow(item, firstRow + i))}
      </ol>
    </div>
  );
}
