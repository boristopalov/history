import { describe, expect, it } from "vitest";
import { momentDate, resultMoments } from "./moments";
import type { Anchor, QueryResult } from "./types";

const at = (ts: number | null): Anchor => ({ ts, location: null });

function result(columns: string[], rows: unknown[][], anchors?: Anchor[]): QueryResult {
  return { columns, rows, anchors: anchors ?? rows.map((_, i) => at(100 + i)), truncated: false };
}

describe("resultMoments", () => {
  it("reads a row of the events table the way the events list shows one", () => {
    const moments = resultMoments(
      result(["ts", "source", "title", "body"], [[100, "messages", "Priya", "dinner at 8?"]]),
    );
    expect(moments).toEqual([
      {
        source: "messages",
        ts: 100,
        primary: "Priya",
        secondary: "dinner at 8?",
        anchor: at(100),
      },
    ]);
  });

  it("takes the time from the anchor, which the server has already validated", () => {
    const moments = resultMoments(result(["ts", "title"], [["not a number", "x"]], [at(42)]));
    expect(moments?.[0].ts).toBe(42);
  });

  it("names the source when a row has only one line of its own", () => {
    const moments = resultMoments(result(["ts", "source", "title"], [[100, "git", "fix bug"]]));
    expect(moments?.[0]).toMatchObject({ primary: "fix bug", secondary: "Commit" });
  });

  it("ignores a source's suffix", () => {
    const moments = resultMoments(result(["ts", "source", "body"], [[100, "receipts.mock", "x"]]));
    expect(moments?.[0].secondary).toBe("Receipt");
  });

  it("puts columns the query added under the main line", () => {
    const moments = resultMoments(
      result(["ts", "title", "fare", "city"], [[100, "Uber", 12.5, "SF"]]),
    );
    expect(moments?.[0]).toMatchObject({ primary: "Uber", secondary: "fare: 12.5 · city: SF" });
  });

  it("makes the added columns the main line when there's nothing else", () => {
    const moments = resultMoments(result(["ts", "source", "fare"], [[100, "receipts", 12.5]]));
    expect(moments?.[0]).toMatchObject({ primary: "fare: 12.5", secondary: "Receipt" });
  });

  it("leaves out empty cells and machine columns", () => {
    const moments = resultMoments(
      result(["ts", "lat", "lon", "data", "note"], [[100, 1, 2, "{}", null]]),
    );
    expect(moments?.[0]).toMatchObject({ primary: "Row", secondary: "" });
  });

  it("finds columns whatever their case", () => {
    const moments = resultMoments(result(["TS", "Title"], [[100, "hello"]]));
    expect(moments?.[0].primary).toBe("hello");
  });

  it("keeps a zero, which is a value and not a blank", () => {
    const moments = resultMoments(result(["ts", "fare"], [[100, 0]]));
    expect(moments?.[0].primary).toBe("fare: 0");
  });

  it("is null for a result without times, like an aggregate", () => {
    expect(resultMoments(result(["source", "n"], [["git", 3]], [null]))).toBeNull();
  });

  it("is null when even one row has no time, rather than dropping that row", () => {
    const rows = [
      [100, "a"],
      [null, "b"],
    ];
    expect(resultMoments(result(["ts", "title"], rows, [at(100), null]))).toBeNull();
    expect(resultMoments(result(["ts", "title"], rows, [at(100), at(null)]))).toBeNull();
  });

  it("is null for an empty result", () => {
    expect(resultMoments(result(["ts"], []))).toBeNull();
  });
});

describe("momentDate", () => {
  it("spells out the year only when it isn't this one", () => {
    const thisYear = new Date().getFullYear();
    const inYear = (year: number) => new Date(year, 5, 15).getTime() / 1000;
    expect(momentDate(inYear(thisYear))).not.toContain(String(thisYear));
    expect(momentDate(inYear(thisYear - 1))).toContain(String(thisYear - 1));
  });
});
