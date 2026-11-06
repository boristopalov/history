import { memo, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { askAgent } from "./api";
import { Icon } from "./icons";
import { resultMoments } from "./moments";
import { ResultTable, resultSummary } from "./ResultTable";
import { ResultView } from "./ResultView";
import type { AgentEvent, Anchor, QueryResult } from "./types";

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

function momentLabel(result: QueryResult): string {
  const count = result.rows.length;
  return `${count}${result.truncated ? "+" : ""} ${count === 1 ? "moment" : "moments"}`;
}

/** What a finished turn found: its last query that can be listed, which is usually the answer. */
function turnResult(turn: Turn): QueryResult | null {
  if (turn.pending) return null;
  for (const part of [...turn.parts].reverse()) {
    if (part.kind === "query" && part.result && resultMoments(part.result)) return part.result;
  }
  return null;
}

function QueryCard({ part, onShow, onOpen, onPick }: {
  part: Extract<Part, { kind: "query" }>;
  onShow: (result: QueryResult) => void;
  onOpen: (result: QueryResult) => void;
  onPick: (anchor: NonNullable<Anchor>) => void;
}) {
  const { result } = part;
  const listable = result ? resultMoments(result) !== null : false;
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
          {listable ? (
            <button className="link" onClick={() => onOpen(result)}>
              View {momentLabel(result)}
            </button>
          ) : (
            <button className="link" onClick={() => onShow(result)}>
              Show on map
            </button>
          )}
        </>
      )}
    </details>
  );
}

/** Memoized, so that a long conversation isn't rerendered on every frame of playback. */
export const AskTab = memo(function AskTab({ tz, onResult, onPick }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [opened, setOpened] = useState<{ question: string; result: QueryResult } | null>(null);
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
    setOpened(null);
    onResult(null);
  };

  const open = (question: string, result: QueryResult) => {
    setOpened({ question, result });
    onResult(result);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void ask(draft);
    }
  };

  return (
    <div className="tab ask-tab">
      {/* With nothing to show, this is hidden and the composer rises to the top as a search box. */}
      <div
        className="conversation"
        ref={scroller}
        aria-live="polite"
        hidden={turns.length === 0}
      >
        {turns.map((turn, i) => {
          const found = turnResult(turn);
          return (
            <article key={i} className="turn">
              <p className="question">{turn.question}</p>
              {turn.parts.map((part, j) =>
                part.kind === "text" ? (
                  <p key={j} className="answer">
                    {part.text}
                  </p>
                ) : (
                  <QueryCard
                    key={j}
                    part={part}
                    onShow={onResult}
                    onOpen={(result) => open(turn.question, result)}
                    onPick={onPick}
                  />
                ),
              )}
              {found && (
                <button className="moments-link" onClick={() => open(turn.question, found)}>
                  <Icon name="pin" />
                  <span>{momentLabel(found)}</span>
                  <Icon name="right" />
                </button>
              )}
              {turn.pending && <div className="typing" aria-label="Working" />}
              {turn.error && <p className="error">{turn.error}</p>}
            </article>
          );
        })}
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
      {/* Laid over the chat rather than replacing it, so going back keeps its scroll position. */}
      {opened && (
        <section className="result-sheet" aria-label="Query result">
          <header className="result-sheet-top">
            <button className="ghost" aria-label="Back to chat" onClick={() => setOpened(null)}>
              <Icon name="left" />
            </button>
            <span title={opened.question}>{opened.question}</span>
          </header>
          <ResultView result={opened.result} onPick={onPick} />
        </section>
      )}
    </div>
  );
});
