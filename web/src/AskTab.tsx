import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { askAgent } from "./api";
import { Icon } from "./icons";
import { ResultTable, resultSummary } from "./ResultTable";
import type { AgentEvent, Anchor, QueryResult } from "./types";

const SUGGESTIONS = [
  "Where did I spend the most time this week?",
  "How much did I spend on rides this month?",
  "What did I do last Saturday?",
];

type Part =
  | { kind: "text"; text: string }
  | { kind: "query"; sql: string; result?: QueryResult; error?: string };

type Turn = { question: string; parts: Part[]; error?: string; pending: boolean };

type Props = {
  tz: string;
  onResult: (result: QueryResult | null) => void;
  onPick: (anchor: NonNullable<Anchor>) => void;
};

function withEvent(turn: Turn, event: AgentEvent): Turn {
  switch (event.type) {
    case "text": {
      const last = turn.parts.at(-1);
      const parts =
        last?.kind === "text"
          ? [...turn.parts.slice(0, -1), { ...last, text: last.text + event.text }]
          : [...turn.parts, { kind: "text" as const, text: event.text }];
      return { ...turn, parts };
    }
    case "query":
      return { ...turn, parts: [...turn.parts, { kind: "query", ...event }] };
    case "error":
      return { ...turn, error: event.message, pending: false };
    case "done":
      return { ...turn, pending: false };
  }
}

function QueryCard({ part, onShow, onPick }: {
  part: Extract<Part, { kind: "query" }>;
  onShow: (result: QueryResult) => void;
  onPick: (anchor: NonNullable<Anchor>) => void;
}) {
  const { result } = part;
  return (
    <details className="query-card">
      <summary>
        <span>Ran a query</span>
        <span className="query-summary">
          {part.error ? "failed" : result ? resultSummary(result) : ""}
        </span>
      </summary>
      <pre>{part.sql}</pre>
      {part.error && <p className="error">{part.error}</p>}
      {result && (
        <>
          <ResultTable result={result} onPick={onPick} />
          <button className="link" onClick={() => onShow(result)}>
            Show on map
          </button>
        </>
      )}
    </details>
  );
}

export function AskTab({ tz, onResult, onPick }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const history = useRef<unknown[]>([]);
  const abort = useRef<AbortController | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const busy = turns.at(-1)?.pending ?? false;

  useEffect(() => {
    const element = scroller.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [turns]);

  useEffect(() => () => abort.current?.abort(), []);

  const updateLast = (change: (turn: Turn) => Turn) =>
    setTurns((all) => [...all.slice(0, -1), change(all[all.length - 1])]);

  const ask = async (question: string) => {
    if (busy || !question.trim()) return;
    setDraft("");
    setTurns((all) => [...all, { question, parts: [], pending: true }]);
    const controller = new AbortController();
    abort.current = controller;
    try {
      await askAgent(
        question,
        history.current,
        tz,
        (event) => {
          if (event.type === "done") history.current = event.messages;
          if (event.type === "query" && event.result?.anchors.some((a) => a?.location)) {
            onResult(event.result);
          }
          updateLast((turn) => withEvent(turn, event));
        },
        controller.signal,
      );
      // A stream that ends with neither `done` nor `error` was cut off.
      updateLast((turn) =>
        turn.pending ? { ...turn, pending: false, error: "The connection dropped." } : turn,
      );
    } catch (failure) {
      if (controller.signal.aborted) {
        updateLast((turn) => ({ ...turn, pending: false, error: "Stopped." }));
      } else {
        const message = failure instanceof Error ? failure.message : "Something went wrong.";
        updateLast((turn) => ({ ...turn, pending: false, error: message }));
      }
    }
  };

  const reset = () => {
    abort.current?.abort();
    history.current = [];
    setTurns([]);
    onResult(null);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void ask(draft);
    }
  };

  return (
    <div className="tab ask-tab">
      <div className="conversation" ref={scroller} aria-live="polite">
        {turns.length === 0 && (
          <div className="suggestions">
            {SUGGESTIONS.map((suggestion) => (
              <button key={suggestion} className="suggestion" onClick={() => void ask(suggestion)}>
                {suggestion}
              </button>
            ))}
          </div>
        )}
        {turns.map((turn, i) => (
          <article key={i} className="turn">
            <p className="question">{turn.question}</p>
            {turn.parts.map((part, j) =>
              part.kind === "text" ? (
                <p key={j} className="answer">
                  {part.text}
                </p>
              ) : (
                <QueryCard key={j} part={part} onShow={onResult} onPick={onPick} />
              ),
            )}
            {turn.pending && <div className="typing" aria-label="Working" />}
            {turn.error && <p className="error">{turn.error}</p>}
          </article>
        ))}
      </div>
      <div className="composer">
        <textarea
          aria-label="Ask about your history"
          placeholder="Ask about your history"
          rows={1}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
        />
        {busy ? (
          <button className="round" aria-label="Stop" onClick={() => abort.current?.abort()}>
            <Icon name="stop" />
          </button>
        ) : (
          <button
            className="round primary"
            aria-label="Send"
            disabled={!draft.trim()}
            onClick={() => void ask(draft)}
          >
            <Icon name="send" />
          </button>
        )}
      </div>
      <div className="composer-note">
        <span>Questions and query results are sent to Anthropic.</span>
        {turns.length > 0 && (
          <button className="link" onClick={reset}>
            New chat
          </button>
        )}
      </div>
    </div>
  );
}
