import type { ReactNode } from "react";
import { AskTab } from "./AskTab";
import { Icon } from "./icons";
import { SqlTab } from "./SqlTab";
import type { Anchor, QueryResult } from "./types";

export type PanelTab = "events" | "ask" | "sql";

const TABS: { id: PanelTab; label: string }[] = [
  { id: "events", label: "Events" },
  { id: "ask", label: "Ask" },
  { id: "sql", label: "SQL" },
];

type Props = {
  open: boolean;
  tab: PanelTab;
  tz: string;
  /** The events tab, which the app only builds while it's showing. */
  events: ReactNode;
  onTab: (tab: PanelTab) => void;
  onToggle: () => void;
  onResult: (result: QueryResult | null) => void;
  onPick: (anchor: NonNullable<Anchor>) => void;
};

export function Panel({ open, tab, tz, events, onTab, onToggle, onResult, onPick }: Props) {
  return (
    <>
      {!open && (
        <button className="panel-open surface" aria-label="Open sidebar" onClick={onToggle}>
          <Icon name="panel" />
        </button>
      )}
      {/* Ask and SQL stay mounted while hidden, which keeps a conversation and a query. */}
      <aside className="panel surface" aria-label="Sidebar" hidden={!open}>
        <header className="panel-top">
          <div className="segmented" role="tablist">
            {TABS.map(({ id, label }) => (
              <button key={id} role="tab" aria-selected={tab === id} onClick={() => onTab(id)}>
                {label}
              </button>
            ))}
          </div>
          <button className="ghost" aria-label="Close sidebar" onClick={onToggle}>
            <Icon name="close" />
          </button>
        </header>
        {tab === "events" && <div className="panel-body">{events}</div>}
        <div className="panel-body" hidden={tab !== "ask"}>
          <AskTab tz={tz} onResult={onResult} onPick={onPick} />
        </div>
        <div className="panel-body" hidden={tab !== "sql"}>
          <SqlTab onResult={onResult} onPick={onPick} />
        </div>
      </aside>
    </>
  );
}
