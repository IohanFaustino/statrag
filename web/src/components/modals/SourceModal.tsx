import React from "react";
import type { Source, HighlightRange } from "../../types";
import FocusModal from "./FocusModal";

// ─── Highlight algorithm ───────────────────────────────────────────────────────

interface TextPart {
  text: string;
  hl?: boolean;
}

function buildHighlightParts(text: string, highlights: HighlightRange[]): TextPart[] {
  if (!highlights || highlights.length === 0) return [{ text }];

  // Convert HighlightRange (char offsets) to [start, end] pairs
  const rawRanges: [number, number][] = highlights
    .map((h) => [h.start, h.end] as [number, number])
    .filter(([a, b]) => a >= 0 && b > a && a < text.length);

  if (rawRanges.length === 0) return [{ text }];

  rawRanges.sort((a, b) => a[0] - b[0]);

  // Merge overlapping ranges
  const merged: [number, number][] = [];
  for (const r of rawRanges) {
    if (merged.length && r[0] <= merged[merged.length - 1][1]) {
      merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], r[1]);
    } else {
      merged.push([...r] as [number, number]);
    }
  }

  const parts: TextPart[] = [];
  let cur = 0;
  for (const [a, b] of merged) {
    const safeB = Math.min(b, text.length);
    if (a > cur) parts.push({ text: text.slice(cur, a) });
    parts.push({ text: text.slice(a, safeB), hl: true });
    cur = safeB;
  }
  if (cur < text.length) parts.push({ text: text.slice(cur) });
  return parts;
}

// Fallback: substring matching when highlights are strings (legacy data)
function buildHighlightPartsFromStrings(text: string, strs: string[]): TextPart[] {
  const ranges: [number, number][] = [];
  for (const s of strs) {
    const idx = text.indexOf(s);
    if (idx >= 0) ranges.push([idx, idx + s.length]);
  }
  return buildHighlightParts(text, ranges.map(([start, end]) => ({ start, end })));
}

// ─── Source modal ─────────────────────────────────────────────────────────────

interface SourceModalProps {
  open: boolean;
  onClose(): void;
  source: Source | null;
  books?: { id: string; short: string }[];
}

export default function SourceModal({
  open,
  onClose,
  source,
  books = [],
}: SourceModalProps) {
  if (!source) return null;

  const tone = source.score >= 0.8 ? "hi" : source.score >= 0.6 ? "mid" : "low";
  const bookKey = source.book.toLowerCase();
  const bookLabel = source.book === "HANSEN" ? "Hansen" : source.book;
  const bookEntry = books.find((b) => b.id === source.book);

  // Build highlight parts — HighlightRange (start/end) preferred; fallback to strings if old format
  const chunkText = source.chunk || "";
  let parts: TextPart[];
  if (source.highlights && source.highlights.length > 0) {
    const first = source.highlights[0];
    if (typeof (first as unknown as { start?: number }).start === "number") {
      parts = buildHighlightParts(chunkText, source.highlights);
    } else {
      // Legacy string array
      parts = buildHighlightPartsFromStrings(
        chunkText,
        source.highlights as unknown as string[],
      );
    }
  } else {
    parts = [{ text: chunkText }];
  }

  return (
    <FocusModal open={open} onClose={onClose} size="md" labelledBy="src-title">
      <header className="fm__hd fm__hd--source">
        <div className="src-modal__top">
          <span className={`book-tag book-tag--${bookKey}`}>
            <span className={`dot dot--${bookKey}`} aria-hidden="true" />
            {bookLabel}
          </span>
          <span className="src-modal__rank">RANK #{source.rank}</span>
          <span className={`score-badge score-badge--${tone}`}>
            {source.score.toFixed(2)}
          </span>
          <span className="src-modal__cid">
            <code>{source.chunkId}</code>
          </span>
        </div>

        <h2 className="fm__title" id="src-title">
          {source.title}
        </h2>

        <div className="src-modal__path">
          <span>{bookEntry ? bookEntry.short : bookLabel}</span>
          <span className="src-modal__sep">/</span>
          <span>{source.chapter}</span>
          <span className="src-modal__sep">/</span>
          <span>{source.section}</span>
          {source.page != null && (
            <>
              <span className="src-modal__sep">·</span>
              <span>p.{source.page}</span>
            </>
          )}
        </div>

        <button
          className="fm__close"
          type="button"
          onClick={onClose}
          aria-label="Close"
        >
          <svg
            viewBox="0 0 16 16"
            width="14"
            height="14"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
          >
            <path d="m4 4 8 8M12 4l-8 8" />
          </svg>
        </button>
      </header>

      <div className="fm__body">
        <div className="src-modal__legend">
          <span className="src-modal__legend-dot" aria-hidden="true" />
          Highlighted spans were used as the matching basis for retrieval.
        </div>

        <div className="src-modal__chunk" aria-label="Source chunk text">
          {parts.map((p, i) =>
            p.hl ? (
              <mark key={i} className="src-hl">
                {p.text}
              </mark>
            ) : (
              <React.Fragment key={i}>{p.text}</React.Fragment>
            ),
          )}
        </div>

        <div className="src-modal__meta">
          <div className="src-modal__meta-row">
            <span>Embedding</span>
            <span>{source.embedding}</span>
          </div>
          <div className="src-modal__meta-row">
            <span>Score</span>
            <span className={`score-text score-text--${tone}`}>
              {source.score.toFixed(4)}
            </span>
          </div>
          <div className="src-modal__meta-row">
            <span>Chunk ID</span>
            <span>
              <code>{source.chunkId}</code>
            </span>
          </div>
          <div className="src-modal__meta-row">
            <span>Highlighted spans</span>
            <span>{source.highlights ? source.highlights.length : 0}</span>
          </div>
        </div>
      </div>

      <footer className="fm__ft">
        <button className="btn" type="button" onClick={onClose}>
          Close
        </button>
        <button className="btn btn--ghost" type="button">
          Open in reader →
        </button>
      </footer>
    </FocusModal>
  );
}
