/** Query result rows as moments, so they can be listed like events. Pure, so it can be tested. */

import { sourceInfo } from "./sources";
import type { Anchor, QueryResult } from "./types";

export type Moment = {
  source: string | null;
  ts: number;
  primary: string;
  secondary: string;
  anchor: NonNullable<Anchor>;
};

const FALLBACK_LABEL = "Row";

// Columns that are either shown some other way, or say nothing to someone reading a list.
const NOT_DETAILS = new Set([
  "ts",
  "end_ts",
  "source",
  "source_id",
  "title",
  "body",
  "url",
  "lat",
  "lon",
  "is_fix",
  "data",
]);

function present(value: unknown): string | null {
  return value === null || value === undefined || value === "" ? null : String(value);
}

/**
 * A result's rows as moments, or null if any row has no time. A list can't show a row like
 * that, and leaving it out would hide part of the result, so such a result stays a table.
 */
export function resultMoments(result: QueryResult): Moment[] | null {
  if (result.rows.length === 0) return null;
  const names = result.columns.map((column) => column.toLowerCase());
  const moments: Moment[] = [];

  for (const [i, row] of result.rows.entries()) {
    const anchor = result.anchors[i];
    if (anchor?.ts === null || anchor?.ts === undefined) return null;

    const cell = (name: string) => present(row[names.lastIndexOf(name)]);
    const source = cell("source");
    const label = source ? sourceInfo(source).label : FALLBACK_LABEL;
    const details = result.columns
      .flatMap((column, j) => {
        const value = present(row[j]);
        return value === null || NOT_DETAILS.has(names[j]) ? [] : [`${column}: ${value}`];
      })
      .join(" · ");

    const [title, body] = [cell("title"), cell("body")];
    const main = title ?? body ?? cell("url");
    let lines: [string, string];
    if (title && body) lines = [title, body];
    else if (main) lines = [main, details || label];
    else if (details) lines = [details, label];
    else lines = [label, ""];

    moments.push({ source, ts: anchor.ts, primary: lines[0], secondary: lines[1], anchor });
  }
  return moments;
}

const THIS_YEAR_DATE = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
const OTHER_YEAR_DATE = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
});

/** A moment's day. A result can span years, so any but this one is spelled out. */
export function momentDate(ts: number): string {
  const date = new Date(ts * 1000);
  const format = date.getFullYear() === new Date().getFullYear() ? THIS_YEAR_DATE : OTHER_YEAR_DATE;
  return format.format(date);
}
