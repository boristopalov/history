/** Everything the UI asks the server. */

import type { AgentEvent, Day, HistoryEvent, QueryResult } from "./types";

const TOKEN_KEY = "history.apiToken";
const PAGE_SIZE = 5000;

function savedToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function send(path: string, init: RequestInit, token: string | null): Promise<Response> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(path, { ...init, headers });
}

/** A server with api_token set answers 401 until it gets one, so ask once and keep it. */
async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const response = await send(path, init, savedToken());
  if (response.status !== 401) return response;
  const token = window.prompt("API token for this server");
  if (!token) return response;
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Not remembered, but it still works for this request.
  }
  return send(path, init, token);
}

async function errorMessage(response: Response): Promise<string> {
  const body = await response.json().catch(() => null);
  return typeof body?.detail === "string" ? body.detail : `Server error (${response.status})`;
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await request(path, { signal });
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

export function fetchDays(tz: string): Promise<Day[]> {
  return getJson(`/days?tz=${encodeURIComponent(tz)}`);
}

/** Every event in a time range. The server pages, so this keeps asking until it runs out. */
export async function fetchEvents(
  start: number,
  end: number,
  signal: AbortSignal,
): Promise<HistoryEvent[]> {
  const events: HistoryEvent[] = [];
  for (;;) {
    // The range is inclusive, and the next day's first second belongs to the next day.
    const params = `start=${start}&end=${end - 0.001}&limit=${PAGE_SIZE}&offset=${events.length}`;
    const page = await getJson<HistoryEvent[]>(`/timeline?${params}`, signal);
    events.push(...page);
    if (page.length < PAGE_SIZE) return events;
  }
}

export async function runQuery(sql: string): Promise<QueryResult> {
  const response = await request("/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sql }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

/** Streams the agent's events, one JSON object per line, to `onEvent`. */
export async function askAgent(
  prompt: string,
  messages: unknown[],
  tz: string,
  onEvent: (event: AgentEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await request("/agent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, messages, tz }),
    signal,
  });
  if (!response.ok || !response.body) throw new Error(await errorMessage(response));

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    buffer += value;
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) if (line) onEvent(JSON.parse(line));
  }
}
