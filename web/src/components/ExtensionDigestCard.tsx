import React, { useState } from "react";
import { MathBlock } from "./Math";
import { renderInlineWithCites } from "./views/TutorView";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ExtensionFootnote {
  marker: string;
  body: string;
  source: string;
  kind: "corpus" | "wikipedia";
}

export interface ExtensionPoint {
  title: string;
  curated_text: string;
  footnotes: ExtensionFootnote[];
}

export interface ExtensionDigest {
  book: string;
  chapter: string;
  points: ExtensionPoint[];
  unfilled_gaps: string[];
}

// ─── Download helper ──────────────────────────────────────────────────────────

async function downloadZip(digest: ExtensionDigest): Promise<void> {
  const res = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(digest),
  });
  if (!res.ok) return;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${digest.book}-${digest.chapter}-extended.zip`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ─── Component ────────────────────────────────────────────────────────────────

interface Props {
  digest: ExtensionDigest;
}

// Empty citation map — curated_text/footnotes use math but not [N] citation markers.
const NO_CITES = new Map();

export default function ExtensionDigestCard({ digest }: Props) {
  // Hover state required by renderInlineWithCites signature (unused here).
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  return (
    <div className="extension-card">
      <div className="extension-card__hd">
        <span className="extension-card__scope">
          {digest.book} · {digest.chapter} — Extended
        </span>
        <button
          type="button"
          className="extension-card__download"
          aria-label="Download ZIP"
          onClick={() => downloadZip(digest)}
        >
          Download ZIP
        </button>
      </div>

      <div className="extension-card__points">
        {digest.points.map((pt, i) => (
          <section key={i} className="extension-point">
            <h3 className="extension-point__title">{pt.title}</h3>
            <div className="extension-point__body">
              {renderInlineWithCites(pt.curated_text, NO_CITES, hoveredIdx, setHoveredIdx)}
            </div>

            {pt.footnotes.length > 0 && (
              <ul className="extension-point__footnotes">
                {pt.footnotes.map((fn, j) => (
                  <li key={j} className="extension-footnote">
                    <sup className="extension-footnote__marker">{fn.marker}</sup>
                    <span className="extension-footnote__body">
                      {renderInlineWithCites(fn.body, NO_CITES, hoveredIdx, setHoveredIdx)}
                    </span>
                    <span className="extension-footnote__source">
                      ({fn.source} · {fn.kind})
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>

      {digest.unfilled_gaps.length > 0 && (
        <div className="extension-card__gaps">
          <h4 className="extension-card__gaps-hd">Unfilled gaps</h4>
          <ul>
            {digest.unfilled_gaps.map((gap, i) => (
              <li key={i}>{gap}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
