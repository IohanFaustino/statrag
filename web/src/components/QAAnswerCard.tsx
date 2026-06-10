import React, { useMemo, useState } from "react";
import type { QAAnswer, TutorCitation } from "../types";
import { MathBlock } from "./Math";
import { renderInlineWithCites } from "./views/TutorView";

interface QAAnswerCardProps {
  answer: QAAnswer;
}

/**
 * Renders a punctual Q&A answer: terse body (with inline [n] citation pills
 * and inline math rendered via the same renderInlineWithCites helper as
 * TutorView), a scope line (what was answered and what was assumed known),
 * math_blocks rendered via MathBlock, and a grounding badge.
 *
 * Handles two shapes:
 *  - Legacy single-call QA: { text, scope, citations, math_blocks, grounding }
 *  - Deepagent QA: { thesis, deepening, synthesis, sub_queries, citations, … }
 * All fields are optional; the component guards every access.
 */
export default function QAAnswerCard({ answer }: QAAnswerCardProps) {
  const { text, scope, citations, math_blocks, grounding } = answer;
  const grounded = grounding?.ok === true;

  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  // Body text: prefer the legacy single-call `text`; otherwise assemble the
  // deepagent thesis → deepening → synthesis progression into one prose block.
  // Either shape can be missing fields, so guard every access.
  const bodyText = useMemo(() => {
    if (typeof text === "string" && text.trim()) return text;
    return [answer.thesis, answer.deepening, answer.synthesis]
      .filter((s): s is string => typeof s === "string" && s.trim().length > 0)
      .join("\n\n");
  }, [text, answer.thesis, answer.deepening, answer.synthesis]);

  const citationsByIndex = useMemo(() => {
    const m = new Map<number, TutorCitation>();
    for (const c of citations ?? []) m.set(c.index, c);
    return m;
  }, [citations]);

  const bodyNodes = useMemo(
    () => renderInlineWithCites(bodyText, citationsByIndex, hoveredIdx, setHoveredIdx),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [bodyText, citationsByIndex, hoveredIdx],
  );

  const assumedKnown = scope?.assumed_known ?? [];

  return (
    <div className="qa-card">
      {scope?.target_gap && (
        <div className="qa-card__scope">
          <span className="qa-card__scope-lbl">Answering:</span>{" "}
          <span className="qa-card__gap">{scope.target_gap}</span>
          {assumedKnown.length > 0 && (
            <span className="qa-card__known">
              {" · assuming you know: "}
              {assumedKnown.join(", ")}
            </span>
          )}
        </div>
      )}
      <div className="qa-card__body">{bodyNodes}</div>
      {(math_blocks ?? []).length > 0 && (
        <div className="qa-card__math-blocks">
          {(math_blocks ?? []).map((tex, i) => (
            <div key={i} className="qa-card__math-block">
              <MathBlock tex={tex} />
            </div>
          ))}
        </div>
      )}
      <div className={"qa-card__badge" + (grounded ? " is-grounded" : " is-partial")}>
        {grounded ? "✓ grounded" : "⚠ partial"}
        {typeof grounding?.confidence === "number" && (
          <span className="qa-card__conf"> ({Math.round(grounding.confidence * 100)}%)</span>
        )}
      </div>
    </div>
  );
}
