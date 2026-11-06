/** How each kind of source appears in a list. */

import type { IconName } from "./icons";
import { sourceKind } from "./track";

export type SourceInfo = { icon: IconName; label: string };

const SOURCES: Record<string, SourceInfo> = {
  app_usage: { icon: "app", label: "App" },
  browser: { icon: "globe", label: "Browsing" },
  calendar: { icon: "calendar", label: "Calendar" },
  events: { icon: "ticket", label: "Invite" },
  git: { icon: "commit", label: "Commit" },
  health: { icon: "heart", label: "Health" },
  messages: { icon: "message", label: "Message" },
  music: { icon: "music", label: "Music" },
  notes: { icon: "note", label: "Note" },
  photos: { icon: "photo", label: "Photo" },
  receipts: { icon: "receipt", label: "Receipt" },
  transactions: { icon: "card", label: "Purchase" },
};

/** A source nobody has given an icon, like a plugin's, still gets a row. */
export function sourceInfo(source: string): SourceInfo {
  return SOURCES[sourceKind(source)] ?? { icon: "dot", label: source };
}
