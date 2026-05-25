import React from "react";
import type { DAG } from "../../types";

interface Props {
  data: DAG;
}

export default function DAGView({ data }: Props) {
  return (
    <div className="dag-view">
      {data.cycles_broken.length > 0 && (
        <div className="dag-warning">
          <span className="dag-warning__icon" aria-hidden="true">⚠</span>
          <span>Cycles broken: {data.cycles_broken.join(", ")}</span>
        </div>
      )}

      <section className="dag-section">
        <h4 className="dag-section__title">Concepts</h4>
        <table className="dag-table" aria-label="Concept nodes">
          <thead>
            <tr>
              <th>ID</th>
              <th>Label</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {data.nodes.map((node) => (
              <tr key={node.id}>
                <td><code>{node.id}</code></td>
                <td>{node.label}</td>
                <td>
                  {node.source
                    ? `${node.source.book} · ${node.source.section}`
                    : <span className="dag-cell--empty">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="dag-section">
        <h4 className="dag-section__title">Prerequisites</h4>
        {data.edges.length === 0 ? (
          <p className="dag-empty">No edges.</p>
        ) : (
          <table className="dag-table" aria-label="Prerequisite edges">
            <thead>
              <tr>
                <th>From</th>
                <th></th>
                <th>To</th>
                <th>Weight</th>
              </tr>
            </thead>
            <tbody>
              {data.edges.map((edge, i) => (
                <tr key={i}>
                  <td><code>{edge.from_id}</code></td>
                  <td className="dag-arrow" aria-hidden="true">→</td>
                  <td><code>{edge.to_id}</code></td>
                  <td>
                    <span className="dag-badge">{edge.weight.toFixed(2)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
