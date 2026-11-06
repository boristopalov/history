/** The arithmetic behind the year heatmap. Pure, so it can be tested alone. */

import { localDate } from "./track";

export const WINDOW_DAYS = 365;

/** A calendar day moved by some days. Going through local dates stays right across DST. */
export function addDays(date: string, days: number): string {
  const [year, month, day] = date.split("-").map(Number);
  return localDate(new Date(year, month - 1, day + days).getTime() / 1000);
}

function weekday(date: string): number {
  const [year, month, day] = date.split("-").map(Number);
  return new Date(year, month - 1, day).getDay();
}

/**
 * The year ending on `end`, as columns of Sunday-to-Saturday weeks. Slots outside the year,
 * at the start of the first week and the end of the last, are null.
 */
export function yearWeeks(end: string): (string | null)[][] {
  const first = addDays(end, 1 - WINDOW_DAYS);
  const weeks: (string | null)[][] = [];
  let date = addDays(first, -weekday(first));
  while (date <= end) {
    const week: (string | null)[] = [];
    for (let i = 0; i < 7; i++) {
      week.push(date >= first && date <= end ? date : null);
      date = addDays(date, 1);
    }
    weeks.push(week);
  }
  return weeks;
}

/** The week columns where a new month begins, with the month's short name. */
export function monthLabels(weeks: (string | null)[][]): { week: number; label: string }[] {
  const labels: { week: number; label: string }[] = [];
  weeks.forEach((days, week) => {
    const first = days.find((date) => date?.endsWith("-01"));
    if (!first) return;
    const [year, month] = first.split("-").map(Number);
    const label = new Date(year, month - 1, 1).toLocaleDateString([], { month: "short" });
    labels.push({ week, label });
  });
  return labels;
}

/**
 * The counts where each color step begins, from the spread of the busy days themselves. A
 * few huge days would otherwise flatten everything else on a linear scale.
 */
export function levelEdges(counts: number[]): number[] {
  const sorted = counts.filter((count) => count > 0).sort((a, b) => a - b);
  if (sorted.length === 0) return [];
  const quantile = (share: number) => sorted[Math.floor(share * (sorted.length - 1))];
  return [...new Set([0.25, 0.5, 0.75, 0.9].map(quantile))];
}

/** 0 for an empty day, then 1 and up. Reaches 5 only on the busiest days. */
export function levelOf(count: number, edges: number[]): number {
  if (count <= 0) return 0;
  return 1 + edges.filter((edge) => count > edge).length;
}
