import React, { useState } from "react";
import { renderMathText, normalizeMathDelimiters } from "../lib/renderRichText";
import type { StoryDigest, StoryCitation } from "../types";

/**
 * Split `normalised` on blank lines, but skip blank lines that fall INSIDE a
 * `$$...$$` display-math block (which can contain blank lines after
 * normalizeMathDelimiters converts `\[...\]`).
 *
 * Algorithm: scan character by character tracking whether we're inside a $$
 * block (toggled every time we encounter `$$`).  A run of two-or-more newlines
 * is a paragraph boundary ONLY when `insideMath` is false at that point.
 */
function splitParagraphsOutsideMath(normalised: string): string[] {
  const chunks: string[] = [];
  let current = "";
  let insideMath = false;
  let i = 0;
  while (i < normalised.length) {
    // Check for $$ delimiter (but not a lone $)
    if (
      normalised[i] === "$" &&
      normalised[i + 1] === "$" &&
      normalised[i + 2] !== "$"
    ) {
      insideMath = !insideMath;
      current += "$$";
      i += 2;
      continue;
    }
    // Check for paragraph break (two or more newlines) outside math
    if (!insideMath && normalised[i] === "\n") {
      let j = i;
      while (j < normalised.length && normalised[j] === "\n") j++;
      if (j - i >= 2) {
        // Genuine paragraph boundary
        chunks.push(current);
        current = "";
        i = j;
        continue;
      }
    }
    current += normalised[i];
    i++;
  }
  chunks.push(current);
  return chunks;
}

/**
 * Split body text on blank lines and render each paragraph through the
 * math+markdown renderer. Blank lines that fall inside `$$...$$` display-math
 * blocks (which `normalizeMathDelimiters` can produce from `\[...\]` source)
 * are skipped — the equation is kept intact as a single chunk.
 */
function renderParagraphs(text: string, className?: string): React.ReactNode {
  const normalised = normalizeMathDelimiters(text);
  const chunks = splitParagraphsOutsideMath(normalised);
  if (chunks.length === 1) {
    // Single paragraph — keep original wrapper behaviour (no extra <p> wrapping)
    return renderMathText(text);
  }
  return (
    <>
      {chunks.map((chunk, i) =>
        chunk.trim() ? (
          <p
            key={i}
            className={className}
            style={{ textAlign: "justify", margin: "0 0 0.6em" }}
          >
            {renderMathText(chunk)}
          </p>
        ) : null
      )}
    </>
  );
}

function Chip({ c }: { c: StoryCitation }) {
  if (c.kind === "wikipedia" && c.url) {
    return (
      <a className="citation-chip citation-chip--wiki" href={c.url}
         target="_blank" rel="noopener noreferrer">🌐 {c.label}</a>
    );
  }
  return <span className="citation-chip citation-chip--corpus" title={c.label}>📕 {c.label}</span>;
}

function StoryDigestCardInner({ digest }: { digest: StoryDigest }) {
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const toggle = (i: number) =>
    setOpen((s) => { const n = new Set(s); n.has(i) ? n.delete(i) : n.add(i); return n; });
  const withItems = digest.takes.map((t, i) => [t, i] as const).filter(([t]) => t.items.length > 0);

  const download = async () => {
    setIsDownloading(true);
    setDownloadError(null);
    try {
      const res = await fetch("/api/export", { method: "POST",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(digest) });
      if (!res.ok) { setDownloadError(`Export failed (${res.status})`); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `${digest.book}-${digest.chapter}-extended.zip`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch {
      setDownloadError("Export failed — network error");
    } finally { setIsDownloading(false); }
  };

  return (
    <div className="story-card">
      <div className="story-card__hd">
        <span className="story-card__scope">{digest.book} · {digest.chapter} — Story</span>
        <button type="button" aria-label="Expand all" onClick={() => setOpen(new Set(withItems.map(([, i]) => i)))}>Expand all</button>
        <button type="button" aria-label="Collapse all" onClick={() => setOpen(new Set())}>Collapse all</button>
        <button type="button" aria-label="Download ZIP" disabled={isDownloading} onClick={download}>
          {isDownloading ? "Downloading…" : "Download ZIP"}
        </button>
        {downloadError && (
          <span className="story-card__download-error" role="alert">{downloadError}</span>
        )}
      </div>

      {digest.takes.map((t, i) => (
        <div key={i} className="story-take">
          {/* Rail: num node + connecting line. mt aligns node with heading first line. */}
          <div className="story-take__rail">
            <div className="story-take__num" style={{ marginTop: "3px" }}>{i + 1}</div>
            {i < digest.takes.length - 1 && <div className="story-take__line" />}
          </div>
          <div className="story-take__body">
            {/* Heading: rendered through math+markdown renderer for $...$ support */}
            <h3 className="story-take__heading" style={{ marginTop: 0, marginBottom: "0.45em" }}>
              {renderMathText(t.heading)}
            </h3>
            {/* Story: multi-paragraph support — \n\n splits into justified <p> blocks */}
            <div className="story-take__story">
              {renderParagraphs(t.story)}
            </div>
            {t.items.length > 0 && (
              <div className="curiosity-box">
                {/* Full-width toggle button — entire header bar is clickable */}
                <button
                  type="button"
                  className="curiosity-box__toggle"
                  aria-expanded={open.has(i)}
                  onClick={() => toggle(i)}
                  style={{ display: "block", width: "100%", textAlign: "left" }}
                >
                  {open.has(i) ? "▾" : "▸"} Curiosity box ({t.items.length})
                </button>
                {open.has(i) && (
                  <ul className="curiosity-box__items">
                    {t.items.map((it, j) => (
                      <li key={j} className="curiosity-item">
                        <span className="curiosity-item__subject">{renderMathText(it.subject)}</span>
                        {/* Body: multi-paragraph support */}
                        <div className="curiosity-item__body">
                          {renderParagraphs(it.body)}
                        </div>
                        <div className="curiosity-item__chips">
                          {it.citations.map((c, k) => <Chip key={k} c={c} />)}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </div>
      ))}

      {digest.unfilled_subjects.length > 0 && (
        <div className="story-card__unfilled">
          <h4>Unfilled subjects</h4>
          <ul>{digest.unfilled_subjects.map((g, i) => <li key={i}>{renderMathText(g)}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

export default function StoryDigestCard(props: { digest: StoryDigest }) {
  return <StoryDigestCardInner {...props} />;
}
