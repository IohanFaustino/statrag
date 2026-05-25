import React, { useState } from "react";
import type { Quiz } from "../../types";

interface Props {
  data: Quiz;
}

export default function QuizView({ data }: Props) {
  const [revealed, setRevealed] = useState<Record<number, boolean>>({});
  const [selected, setSelected] = useState<Record<number, number>>({});

  function toggle(i: number) {
    setRevealed((prev) => ({ ...prev, [i]: !prev[i] }));
  }

  return (
    <div className="qz-list">
      {data.questions.map((q, i) => {
        const isRevealed = !!revealed[i];
        const userPick = selected[i];
        return (
          <div key={i} className="qz-card">
            <div className="qz-card__header">
              <span className="qz-card__num">{i + 1}</span>
              <span className={`qz-card__diff qz-card__diff--${q.difficulty}`}>{q.difficulty}</span>
              <span className="qz-card__src">
                {q.source.book} · {q.source.section}
                {q.source.page != null ? ` · p.${q.source.page}` : ""}
              </span>
            </div>

            <p className="qz-card__stem">{q.stem}</p>

            <div className="qz-card__options">
              {q.options.map((opt, j) => {
                const isCorrect = j === q.answer_idx;
                const isPicked = userPick === j;
                let cls = "qz-option";
                if (isRevealed && isCorrect) cls += " qz-option--correct";
                if (isRevealed && isPicked && !isCorrect) cls += " qz-option--wrong";
                if (!isRevealed && isPicked) cls += " qz-option--picked";
                return (
                  <button
                    key={j}
                    type="button"
                    className={cls}
                    onClick={() => !isRevealed && setSelected((prev) => ({ ...prev, [i]: j }))}
                    aria-pressed={isPicked}
                    aria-disabled={isRevealed}
                  >
                    <span className="qz-option__letter">{String.fromCharCode(65 + j)}</span>
                    <span className="qz-option__text">{opt}</span>
                  </button>
                );
              })}
            </div>

            {isRevealed && (
              <div className="qz-card__rubric">
                <span className="qz-card__rubric-label">Rubric</span>
                <p>{q.rubric}</p>
              </div>
            )}

            <button
              type="button"
              className="qz-card__reveal"
              onClick={() => toggle(i)}
            >
              {isRevealed ? "Hide answer" : "Reveal answer"}
            </button>
          </div>
        );
      })}
    </div>
  );
}
