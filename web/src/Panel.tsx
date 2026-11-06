import { memo, useState } from "react";
import { AskTab } from "./AskTab";
import { Icon } from "./icons";
import { SqlTab } from "./SqlTab";
import type { Anchor, QueryResult } from "./types";

type Props = {
  open: boolean;
  tz: string;
  onToggle: () => void;
  onResult: (result: QueryResult | null) => void;
  onPick: (anchor: NonNullable<Anchor>) => void;
};

/** Memoized, so that a big result table isn't rerendered on every frame of playback. */
export const Panel = memo(function Panel({ open, tz, onToggle, onResult, onPick }: Props) {
  const [tab, setTab] = useState<"ask" | "sql">("ask");

  if (!open) {
    return (
      <button className="panel-open surface" aria-label="Open search" onClick={onToggle}>
        <Icon name="panel" />
      </button>
    );
  }

  return (
    <aside className="panel surface" aria-label="Search">
      <header className="panel-top">
        <div className="segmented" role="tablist">
          <button role="tab" aria-selected={tab === "ask"} onClick={() => setTab("ask")}>
            Ask
          </button>
          <button role="tab" aria-selected={tab === "sql"} onClick={() => setTab("sql")}>
            SQL
          </button>
        </div>
        <button className="ghost" aria-label="Close search" onClick={onToggle}>
          <Icon name="close" />
        </button>
      </header>
      {/* Both stay mounted, so switching tabs keeps a conversation and a query. */}
      <div className="panel-body" hidden={tab !== "ask"}>
        <AskTab tz={tz} onResult={onResult} onPick={onPick} />
      </div>
      <div className="panel-body" hidden={tab !== "sql"}>
        <SqlTab onResult={onResult} onPick={onPick} />
      </div>
    </aside>
  );
});
