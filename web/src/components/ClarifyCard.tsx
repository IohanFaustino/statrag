import React from "react";
import type { ClarifyData } from "../types";

interface Props {
  data: ClarifyData;
  onPick: (slug: string, chapter: string, sections: string[]) => void;
}

export default function ClarifyCard({ data, onPick }: Props) {
  return (
    <div className="clarify-card">
      <p className="clarify-card__msg">{data.message}</p>
      <div className="clarify-card__chips">
        {data.candidates.map((c) => (
          <button
            key={c.slug}
            type="button"
            className="clarify-card__chip"
            onClick={() => onPick(c.slug, data.chapter_guess, data.sections_guess)}
          >
            <span className="clarify-card__chip-name">{c.name}</span>
            <span className="clarify-card__chip-auth">{c.authors_short}</span>
          </button>
        ))}
      </div>
      {data.chapter_guess && (
        <p className="clarify-card__guess">
          Guessed chapter <strong>{data.chapter_guess}</strong>
          {data.sections_guess.length > 0 && <> · sections {data.sections_guess.join(", ")}</>}
        </p>
      )}
    </div>
  );
}
