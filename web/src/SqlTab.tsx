import { memo, useState, type KeyboardEvent } from "react";
import { runQuery } from "./api";
import { ResultView } from "./ResultView";
import type { Anchor, QueryResult } from "./types";

const STARTER = `SELECT ts, source, title, body
FROM events
WHERE is_fix = 0
ORDER BY ts DESC
LIMIT 50`;

type Props = {
  onResult: (result: QueryResult | null) => void;
  onPick: (anchor: NonNullable<Anchor>) => void;
};

/** Memoized, so that a big result isn't rerendered on every frame of playback. */
export const SqlTab = memo(function SqlTab({ onResult, onPick }: Props) {
  const [sql, setSql] = useState(STARTER);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const run = async () => {
    if (running || !sql.trim()) return;
    setRunning(true);
    setError(null);
    try {
      const next = await runQuery(sql);
      setResult(next);
      onResult(next);
    } catch (failure) {
      setResult(null);
      onResult(null);
      setError(failure instanceof Error ? failure.message : "The query failed.");
    } finally {
      setRunning(false);
    }
  };

  const clear = () => {
    setResult(null);
    setError(null);
    onResult(null);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      void run();
    }
  };

  return (
    <div className="tab sql-tab">
      <textarea
        className="sql-input"
        aria-label="SQL query"
        spellCheck={false}
        rows={6}
        value={sql}
        onChange={(event) => setSql(event.target.value)}
        onKeyDown={onKeyDown}
      />
      <div className="sql-actions">
        <span className="hint">
          events(source, ts, end_ts, title, body, url, lat, lon, is_fix, data)
        </span>
        <button className="primary" onClick={() => void run()} disabled={running}>
          {running ? "Running…" : "Run"}
          <kbd>⌘↵</kbd>
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {result && (
        <ResultView
          result={result}
          onPick={onPick}
          actions={
            <button className="link" onClick={clear}>
              Clear
            </button>
          }
        />
      )}
    </div>
  );
});
