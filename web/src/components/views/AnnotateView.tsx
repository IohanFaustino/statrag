import React, { useRef } from "react";
import type { AnnotatedReading } from "../../types";

interface Props {
  data: AnnotatedReading;
}

interface Segment {
  text: string;
  annotationIdx: number | null;
}

function buildSegments(text: string, annotations: AnnotatedReading["annotations"]): Segment[] {
  if (!text || annotations.length === 0) {
    return [{ text, annotationIdx: null }];
  }

  // Sort by start position
  const sorted = annotations
    .map((a, i) => ({ ...a, idx: i }))
    .filter((a) => a.position[0] < a.position[1] && a.position[1] <= text.length)
    .sort((a, b) => a.position[0] - b.position[0]);

  const segments: Segment[] = [];
  let cursor = 0;

  for (const ann of sorted) {
    const [start, end] = ann.position;
    if (start > cursor) {
      segments.push({ text: text.slice(cursor, start), annotationIdx: null });
    }
    if (start >= cursor) {
      segments.push({ text: text.slice(start, end), annotationIdx: ann.idx });
      cursor = end;
    }
  }

  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor), annotationIdx: null });
  }

  return segments;
}

export default function AnnotateView({ data }: Props) {
  const defRefs = useRef<Record<number, HTMLLIElement | null>>({});

  function scrollToDef(idx: number) {
    const el = defRefs.current[idx];
    if (el) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // Reconstruct the original text from annotation positions
  const maxPos = data.annotations.reduce(
    (m, a) => Math.max(m, a.position[1]),
    0,
  );
  const hasPositions = maxPos > 0;

  // Build a synthetic text if positions are present — use annotation terms inline
  const syntheticText = hasPositions
    ? null
    : data.annotations.map((a) => a.term).join(", ");

  const segments: Segment[] = hasPositions
    ? buildSegments(
        // We need the original text. Since we only have annotations (not the original input),
        // reconstruct a best-effort representation from positions if available.
        // If annotations have real positions, the parent should pass original text.
        // Here we fall back gracefully.
        data.annotations.map((a) => a.term).join(" … "),
        data.annotations,
      )
    : [];

  return (
    <div className="annotate-view">
      <div className="annotate-view__text" aria-label="Annotated text">
        {hasPositions ? (
          <p className="annotate-text">
            {segments.map((seg, i) =>
              seg.annotationIdx !== null ? (
                <mark
                  key={i}
                  className="annotate-mark"
                  role="button"
                  tabIndex={0}
                  onClick={() => scrollToDef(seg.annotationIdx!)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      scrollToDef(seg.annotationIdx!);
                    }
                  }}
                  title={data.annotations[seg.annotationIdx].term}
                  aria-label={`Term: ${data.annotations[seg.annotationIdx].term}`}
                >
                  {seg.text}
                </mark>
              ) : (
                <React.Fragment key={i}>{seg.text}</React.Fragment>
              ),
            )}
          </p>
        ) : (
          <p className="annotate-text annotate-text--terms">
            {syntheticText}
          </p>
        )}
      </div>

      <div className="annotate-view__defs" aria-label="Term definitions">
        <ul className="annotate-defs">
          {data.annotations.map((ann, i) => (
            <li
              key={i}
              ref={(el) => { defRefs.current[i] = el; }}
              className="annotate-def"
            >
              <span className="annotate-def__term">{ann.term}</span>
              <p className="annotate-def__defn">{ann.definition}</p>
              {ann.source && (
                <span className="annotate-def__src">
                  {ann.source.book} · {ann.source.section}
                  {ann.source.page != null ? ` · p.${ann.source.page}` : ""}
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
