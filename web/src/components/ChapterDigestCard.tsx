import React, { useMemo, useState } from "react";
import type { ChapterDigest, TutorCitation } from "../types";
import { MathBlock } from "./Math";
import { renderInlineWithCites } from "./views/TutorView";

interface Props {
  digest: ChapterDigest;
}

export default function ChapterDigestCard({ digest }: Props) {
  const fuzzy = digest.scope.resolution.filter((r) => r.matched_h2 && r.score < 0.95);
  const conf = digest.grounding?.confidence ?? 0;
  const grounded = digest.grounding?.ok === true && conf >= 0.7;

  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);

  // Build citation lookup shared across all blocks (citations are aggregated
  // across all sections in the digest).
  const citationsByIndex = useMemo(() => {
    const m = new Map<number, TutorCitation>();
    for (const c of digest.citations ?? []) m.set(c.index, c);
    return m;
  }, [digest.citations]);

  const handleDownload = async () => {
    setIsDownloading(true);
    try {
      const res = await fetch("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(digest),
      });
      if (!res.ok) throw new Error(`Export failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const cd = res.headers.get("content-disposition");
      const match = cd?.match(/filename="?([^"]+)"?/);
      a.download = match?.[1] || `${digest.scope.book_slug}-${digest.scope.chapter_id}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className={`chapter-card chapter-card--${digest.mode}`}>
      <div className="chapter-card__hd">
        <span className="chapter-card__mode">
          {digest.mode === "facilitate" ? "Facilitate" : "Resume"}
        </span>
        <span className="chapter-card__scope">
          {digest.scope.book_slug} · {digest.scope.chapter_id}
        </span>
        <span
          className={`chapter-card__badge ${grounded ? "is-ok" : "is-partial"}`}
          data-testid="chapter-grounding-badge"
          title={`grounding confidence ${conf.toFixed(2)}`}
        >
          {grounded ? "✓ grounded" : "⚠ partial"}
        </span>
        <button type="button" className="chapter-card__download" onClick={handleDownload} disabled={isDownloading} aria-label="Download ZIP" title="Download ZIP">{isDownloading ? "…" : "↓"}</button>
      </div>

      {fuzzy.length > 0 && (
        <p className="chapter-card__resolution">
          {fuzzy.map((r) => `interpreted "${r.asked}" as ${r.matched_h2}`).join("; ")}
        </p>
      )}

      {digest.intro && <p className="chapter-card__intro">{digest.intro}</p>}

      <div className="chapter-card__blocks">
        {digest.blocks.map((b, i) => (
          <section key={`${b.section_id}-${i}`} className="chapter-block">
            <h3 className="chapter-block__h">{b.h2_path}</h3>
            {b.page_from > 0 && (
              <span className="chapter-block__pages">
                pp. {b.page_from}
                {b.page_to > b.page_from ? `–${b.page_to}` : ""}
              </span>
            )}
            <div className="chapter-block__body">
              {renderInlineWithCites(b.body, citationsByIndex, hoveredIdx, setHoveredIdx)}
            </div>
          </section>
        ))}
      </div>

      {digest.math_blocks.length > 0 && (
        <div className="chapter-card__math-blocks">
          {digest.math_blocks.map((tex, i) => (
            <div key={i} className="chapter-card__math-block">
              <MathBlock tex={tex} />
            </div>
          ))}
        </div>
      )}

      {digest.outro && <p className="chapter-card__outro">{digest.outro}</p>}
    </div>
  );
}
