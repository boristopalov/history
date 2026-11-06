import { describe, expect, it } from "vitest";
import { addDays, levelEdges, levelOf, monthLabels, WINDOW_DAYS, yearWeeks } from "./calendar";

describe("addDays", () => {
  it("crosses months, years and DST changes", () => {
    expect(addDays("2026-01-31", 1)).toBe("2026-02-01");
    expect(addDays("2026-01-01", -1)).toBe("2025-12-31");
    expect(addDays("2026-10-31", 2)).toBe("2026-11-02");
    expect(addDays("2026-03-07", 2)).toBe("2026-03-09");
  });
});

describe("yearWeeks", () => {
  const weeks = yearWeeks("2026-11-05");
  const dates = weeks.flat().filter((date) => date !== null);

  it("covers exactly the year, in order, ending on the given day", () => {
    expect(dates).toHaveLength(WINDOW_DAYS);
    expect(dates.at(-1)).toBe("2026-11-05");
    expect(dates[0]).toBe("2025-11-06");
    expect(new Set(dates).size).toBe(WINDOW_DAYS);
  });

  it("puts every day in the right row of a Sunday-first week", () => {
    expect(weeks.every((week) => week.length === 7)).toBe(true);
    const sunday = weeks[1][0] as string;
    const [year, month, day] = sunday.split("-").map(Number);
    expect(new Date(year, month - 1, day).getDay()).toBe(0);
    // 2026-11-05 is a Thursday.
    expect(weeks.at(-1)?.indexOf("2026-11-05")).toBe(4);
  });
});

describe("monthLabels", () => {
  it("marks the column holding each month's first day", () => {
    const weeks = yearWeeks("2026-11-05");
    const labels = monthLabels(weeks);
    expect(labels).toHaveLength(12);
    for (const { week } of labels) {
      expect(weeks[week].some((date) => date?.endsWith("-01"))).toBe(true);
    }
  });
});

describe("levels", () => {
  it("leaves empty days at 0 and spreads the rest", () => {
    const counts = Array.from({ length: 100 }, (_, i) => i + 1);
    const edges = levelEdges([0, 0, ...counts]);
    expect(levelOf(0, edges)).toBe(0);
    expect(levelOf(1, edges)).toBe(1);
    expect(levelOf(100, edges)).toBe(5);
  });

  it("isn't flattened by one enormous day", () => {
    const edges = levelEdges([...Array.from({ length: 100 }, (_, i) => i + 1), 100000]);
    expect(levelOf(60, edges)).toBeGreaterThan(levelOf(10, edges));
    expect(levelOf(100000, edges)).toBe(5);
  });

  it("copes with no data and with days that are all the same", () => {
    expect(levelEdges([])).toEqual([]);
    expect(levelEdges([0, 0])).toEqual([]);
    const edges = levelEdges([6, 6, 6]);
    expect(levelOf(6, edges)).toBe(1);
  });
});
