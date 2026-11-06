/** The shapes the server sends. */

export type Location = { lat: number; lon: number; via: string; gap_s: number };

export type HistoryEvent = {
  source: string;
  source_id: string;
  ts: number;
  end_ts: number | null;
  title: string | null;
  body: string | null;
  url: string | null;
  lat: number | null;
  lon: number | null;
  is_fix: boolean;
  location: Location | null;
};

/** `activity` is `events` without bare location pings, which are the path. */
export type Day = { date: string; events: number; fixes: number; activity: number };

/** When and where a query result row happened. Null when its columns don't say. */
export type Anchor = { ts: number | null; location: Location | null } | null;

export type QueryResult = {
  columns: string[];
  rows: unknown[][];
  anchors: Anchor[];
  truncated: boolean;
};

export type AgentEvent =
  | { type: "text"; text: string }
  | { type: "query"; sql: string; result?: QueryResult; error?: string }
  | { type: "done"; messages: unknown[] }
  | { type: "error"; message: string };
