import React from "react";
import type { NavigationList } from "../../types";

interface ChipData { book: string; section: string }

interface Props {
  data: NavigationList;
  onSourceClick?: (chip: ChipData) => void;
}

export default function NavigationView({ data, onSourceClick }: Props) {
  return (
    <div className="nav-view">
      <table className="dag-table nav-table" aria-label="Navigation results">
        <thead>
          <tr>
            <th>Book</th>
            <th>Chapter</th>
            <th>Section</th>
            <th>Title</th>
            <th>Score</th>
            {data.results.some((r) => r.page != null) && <th>Page</th>}
          </tr>
        </thead>
        <tbody>
          {data.results.map((result, i) => (
            <tr
              key={i}
              className="nav-table__row"
              role="button"
              tabIndex={0}
              onClick={() => onSourceClick?.({ book: result.book, section: result.section })}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSourceClick?.({ book: result.book, section: result.section });
                }
              }}
              aria-label={`Open ${result.book} ${result.section}`}
            >
              <td>
                <span className={`dot dot--${result.book.toLowerCase()}`} aria-hidden="true" />
                {result.book}
              </td>
              <td>{result.chapter}</td>
              <td><code>{result.section}</code></td>
              <td>{result.title}</td>
              <td>
                <span className="nav-score">{(result.score * 100).toFixed(0)}%</span>
              </td>
              {data.results.some((r) => r.page != null) && (
                <td>{result.page != null ? result.page : "—"}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
