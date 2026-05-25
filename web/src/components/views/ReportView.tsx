import React from "react";
import type { Report } from "../../types";

interface Props {
  data: Report;
}

export default function ReportView({ data }: Props) {
  return (
    <div className="report-view">
      <div className="report-view__claims">
        <h4 className="report-section__title">Claims</h4>
        {data.claims.map((claim, i) => (
          <div key={i} className="report-claim">
            <div className="report-claim__header">
              <span className={`stance--${claim.stance} report-claim__stance`}>
                {claim.stance}
              </span>
              <span className="report-claim__conf">
                {(claim.confidence * 100).toFixed(0)}% confidence
              </span>
            </div>
            <p className="report-claim__text">{claim.claim}</p>
            {claim.evidence.length > 0 && (
              <ul className="report-claim__evidence">
                {claim.evidence.map((cit, j) => (
                  <li key={j} className="report-claim__cit">
                    {cit.book} · {cit.section}
                    {cit.page != null ? ` · p.${cit.page}` : ""}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>

      <div className="report-view__right">
        <h4 className="report-section__title">Synthesis</h4>
        <p className="report-synthesis">{data.synthesis}</p>

        {data.coverage_gaps.length > 0 && (
          <>
            <h4 className="report-section__title">Coverage Gaps</h4>
            <ul className="report-gaps">
              {data.coverage_gaps.map((gap, i) => (
                <li key={i} className="coverage-gap">{gap}</li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
