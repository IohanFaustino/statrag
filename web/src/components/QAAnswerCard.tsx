import type { QAAnswer } from "../types";

interface QAAnswerCardProps {
  answer: QAAnswer;
}

/**
 * Renders a punctual Q&A answer: terse body, a scope line (what was answered
 * and what was assumed known), and a grounding badge. Citation pills are
 * rendered by the existing citation renderer in MessageThread; this card
 * focuses on the Q&A-specific framing.
 */
export default function QAAnswerCard({ answer }: QAAnswerCardProps) {
  const { text, scope, grounding } = answer;
  const grounded = grounding?.ok === true;
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
      <div className="qa-card__body">{text}</div>
      <div className={"qa-card__badge" + (grounded ? " is-grounded" : " is-partial")}>
        {grounded ? "✓ grounded" : "⚠ partial"}
        {typeof grounding?.confidence === "number" && (
          <span className="qa-card__conf"> ({Math.round(grounding.confidence * 100)}%)</span>
        )}
      </div>
    </div>
  );
}
