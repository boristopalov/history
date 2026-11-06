import { memo, useMemo, useState, type ReactNode } from "react";
import { momentDate, resultMoments, type Moment } from "./moments";
import { ResultTable, resultSummary } from "./ResultTable";
import { Row, RowList } from "./Rows";
import { formatClock } from "./track";
import type { Anchor, QueryResult } from "./types";

type Props = {
  result: QueryResult;
  onPick: (anchor: NonNullable<Anchor>) => void;
  actions?: ReactNode;
};

const MomentRow = memo(function MomentRow({ moment, index, total, picked, onPick }: {
  moment: Moment;
  index: number;
  total: number;
  picked: boolean;
  onPick: (moment: Moment) => void;
}) {
  return (
    <Row
      index={index}
      total={total}
      source={moment.source}
      primary={moment.primary}
      secondary={moment.secondary}
      date={momentDate(moment.ts)}
      time={formatClock(moment.ts, Infinity).slice(0, 5)}
      active={picked}
      onClick={() => onPick(moment)}
    />
  );
});

/** A query's result: a list of moments when every row has a time, and always a raw table. */
export function ResultView({ result, onPick, actions }: Props) {
  const moments = useMemo(() => resultMoments(result), [result]);
  const [view, setView] = useState<"list" | "table">("list");
  const [picked, setPicked] = useState<Moment | null>(null);

  const pick = (moment: Moment) => {
    setPicked(moment);
    onPick(moment.anchor);
  };

  return (
    <div className="result-view">
      <div className="result-bar">
        <span>{resultSummary(result)}</span>
        <span className="result-actions">
          {moments && (
            <div className="segmented small" role="tablist" aria-label="Show result as">
              <button
                role="tab"
                aria-selected={view === "list"}
                onClick={() => setView("list")}
              >
                List
              </button>
              <button
                role="tab"
                aria-selected={view === "table"}
                onClick={() => setView("table")}
              >
                Table
              </button>
            </div>
          )}
          {actions}
        </span>
      </div>
      {moments && view === "list" ? (
        <RowList
          items={moments}
          resetOn={moments}
          renderRow={(moment, index) => (
            <MomentRow
              key={index}
              moment={moment}
              index={index}
              total={moments.length}
              picked={moment === picked}
              onPick={pick}
            />
          )}
        />
      ) : (
        <ResultTable result={result} onPick={onPick} />
      )}
    </div>
  );
}
