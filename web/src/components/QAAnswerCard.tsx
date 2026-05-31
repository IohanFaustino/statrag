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
 */
export default function QAAnswerCard({ answer }: QAAnswerCardProps) {
  const { text, scope, citations, math_blocks, grounding } = answer;
  const grounded = grounding?.ok === true;

  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const citationsByIndex = useMemo(() => {
    const m = new Map<number, TutorCitation>();
    for (const c of citations ?? []) m.set(c.index, c);
    return m;
  }, [citations]);

  const bodyNodes = useMemo(
    () => renderInlineWithCites(text, citationsByIndex, hoveredIdx, setHoveredIdx),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [text, citationsByIndex, hoveredIdx],
  );

  return (
    <div className="qa-card">
      <div className="qa-card__scope">
        <span className="qa-card__scope-lbl">Answering:</span>{" "}
        <span className="qa-card__gap">{scope.target_gap}</span>
        {scope.assumed_known.length > 0 && (
          <span className="qa-card__known">
            {" · assuming you know: "}
            {scope.assumed_known.join(", ")}
          </span>
        )}
      </div>
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
