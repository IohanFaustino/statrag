import React from "react";
import type { StudyPlan } from "../../types";

interface Props {
  data: StudyPlan;
}

export default function StudyPathView({ data }: Props) {
  return (
    <div className="study-view">
      <div className="study-view__header">
        <h4 className="study-view__goal">{data.goal}</h4>
        {data.replanned_from_version > 0 && (
          <span className="study-view__replan">
            replanned from v{data.replanned_from_version}
          </span>
        )}
      </div>

      <div className="study-view__timeline">
        {data.weeks.map((week) => (
          <div key={week.week} className="study-week">
            <div className="study-week__label">
              <span className="study-week__num">Week {week.week}</span>
              <span className="study-week__hours">{week.hours_est}h</span>
            </div>
            <ul className="study-week__sections">
              {week.sections.map((cit, i) => (
                <li key={i} className="study-week__cit">
                  <code>{cit.book}</code>
                  <span className="study-week__cit-sep">·</span>
                  <span>{cit.section}</span>
                  {cit.page != null && (
                    <span className="study-week__page">p.{cit.page}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {data.coverage_gaps.length > 0 && (
        <div className="study-gaps-banner">
          <span className="study-gaps-banner__label">Coverage gaps</span>
          <ul className="study-gaps-banner__list">
            {data.coverage_gaps.map((gap, i) => (
              <li key={i} className="coverage-gap">{gap}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
