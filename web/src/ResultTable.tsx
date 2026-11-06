import type { Anchor, QueryResult } from "./types";

type Props = {
  result: QueryResult;
  onPick: (anchor: NonNullable<Anchor>) => void;
};

function formatCell(column: string, value: unknown): string {
  if (value === null || value === undefined) return "";
  const isTime = ["ts", "end_ts"].includes(column.toLowerCase());
  if (isTime && typeof value === "number") {
    return new Date(value * 1000).toLocaleString([], {
      dateStyle: "short",
      timeStyle: "short",
    });
  }
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

export function ResultTable({ result, onPick }: Props) {
  if (result.columns.length === 0) return null;
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {result.columns.map((column, i) => (
              <th key={i}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row, i) => {
            const anchor = result.anchors[i];
            return (
              <tr
                key={i}
                className={anchor ? "pickable" : undefined}
                onClick={anchor ? () => onPick(anchor) : undefined}
              >
                {row.map((value, j) => {
                  const text = formatCell(result.columns[j], value);
                  return (
                    <td key={j} title={text}>
                      {text}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function resultSummary(result: QueryResult): string {
  const count = result.rows.length;
  const rows = `${count}${result.truncated ? "+" : ""} ${count === 1 ? "row" : "rows"}`;
  const placed = result.anchors.filter((anchor) => anchor?.location).length;
  return placed > 0 ? `${rows} · ${placed} on map` : rows;
}
