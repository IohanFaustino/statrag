import React from "react";
import type { ConceptAnchor } from "../types";
import { MathInline, MathBlock } from "./Math";
import { splitIntoBlocks } from "./views/TutorView";

// ─── Math delimiter normalizer ─────────────────────────────────────────────
// Converts LaTeX-style delimiters to dollar-sign delimiters used by MathInline/MathBlock:
//   \( ... \)  →  $ ... $
//   \[ ... \]  →  $$ ... $$
export function normalizeMath(s: string): string {
  // Order matters: handle \[ \] before \( \) to avoid partial matches.
  // Use global replacement: \[ → $$, \] → $$
  let result = s;
  result = result.replace(/\\\[/g, "$$$$"); // \[ → $$  (each $$ = literal $ in replace)
  result = result.replace(/\\\]/g, "$$$$"); // \] → $$
  result = result.replace(/\\\(/g, "$");    // \( → $
  result = result.replace(/\\\)/g, "$");    // \) → $
  return result;
}

// ─── Inline renderer ───────────────────────────────────────────────────────
// Tokenises a single line of text into: $$…$$, $…$, [[cN]] anchors, and plain text.
function renderInline(
  text: string,
  byId: Map<string, ConceptAnchor>,
  onPick: ((a: ConceptAnchor) => void) | undefined,
): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < text.length) {
    // ── $$...$$ display math (inline occurrence, e.g. inside a paragraph)
    if (text[i] === "$" && text[i + 1] === "$") {
      const end = text.indexOf("$$", i + 2);
      if (end !== -1) {
        const tex = text.slice(i + 2, end);
        out.push(<MathBlock key={key++} tex={tex} />);
        i = end + 2;
        continue;
      }
    }
    // ── $...$ inline math
    if (text[i] === "$") {
      const end = text.indexOf("$", i + 1);
      if (end !== -1) {
        const tex = text.slice(i + 1, end);
        out.push(<MathInline key={key++} tex={tex} />);
        i = end + 1;
        continue;
      }
    }
    // ── [[cN]] concept anchor
    if (text[i] === "[" && text[i + 1] === "[") {
      const close = text.indexOf("]]", i + 2);
      if (close !== -1) {
        const id = text.slice(i + 2, close);
        const anchor = byId.get(id);
        if (anchor) {
          out.push(
            <button
              key={key++}
              type="button"
              className={`concept-anchor concept-anchor--${anchor.kind}`}
              onClick={() => onPick?.(anchor)}
            >
              {anchor.term}
            </button>,
          );
        } else {
          // Unmatched marker → emit as raw text (no crash)
          out.push(
            <React.Fragment key={key++}>{text.slice(i, close + 2)}</React.Fragment>,
          );
        }
        i = close + 2;
        continue;
      }
    }
    // ── Bold **…**
    if (text[i] === "*" && text[i + 1] === "*") {
      const end = text.indexOf("**", i + 2);
      if (end !== -1) {
        out.push(<strong key={key++}>{text.slice(i + 2, end)}</strong>);
        i = end + 2;
        continue;
      }
    }
    // ── Italic *…*
    if (text[i] === "*") {
      const m = text.slice(i).match(/^\*([^*\n]+)\*/);
      if (m) {
        out.push(<em key={key++}>{m[1]}</em>);
        i += m[0].length;
        continue;
      }
    }
    // ── Plain text run until next special char
    let j = i + 1;
    while (
      j < text.length &&
      text[j] !== "$" &&
      text[j] !== "[" &&
      text[j] !== "*" &&
      text[j] !== "\\"
    ) {
      j++;
    }
    out.push(<React.Fragment key={key++}>{text.slice(i, j)}</React.Fragment>);
    i = j;
  }

  return out;
}

// ─── Component ─────────────────────────────────────────────────────────────

interface Props {
  text: string;
  concepts?: ConceptAnchor[];   // [[cN]] → button; omit/empty = no anchors
  onPick?: (a: ConceptAnchor) => void;
}

export default function FacilitateContent({ text, concepts = [], onPick }: Props) {
  const byId = new Map(concepts.map((c) => [c.id, c]));
  const blocks = splitIntoBlocks(normalizeMath(text));

  const rendered = blocks.map((block, i) => {
    if (block.kind === "math") {
      return (
        <div key={i} className="facilitate-content__math-block">
          <MathBlock tex={block.tex} />
        </div>
      );
    }
    if (block.kind === "list") {
      const Tag = block.ordered ? "ol" : "ul";
      return (
        <Tag key={i} className="facilitate-content__list">
          {block.items.map((item, j) => (
            <li key={j}>{renderInline(item, byId, onPick)}</li>
          ))}
        </Tag>
      );
    }
    if (block.kind === "h2") {
      return (
        <h2 key={i} className="facilitate-content__h2">
          {renderInline(block.text, byId, onPick)}
        </h2>
      );
    }
    if (block.kind === "h3") {
      return (
        <h3 key={i} className="facilitate-content__h3">
          {renderInline(block.text, byId, onPick)}
        </h3>
      );
    }
    if (block.kind === "quote") {
      return (
        <blockquote key={i} className="facilitate-content__quote">
          {renderInline(block.text, byId, onPick)}
        </blockquote>
      );
    }
    if (block.kind === "image") {
      return (
        <figure key={i} className="facilitate-content__figure">
          <img src={block.url} alt={block.alt} loading="lazy" style={{ maxWidth: "100%", height: "auto" }} />
          {block.alt && <figcaption>{block.alt}</figcaption>}
        </figure>
      );
    }
    // Default: para
    return (
      <p key={i} className="facilitate-content__para">
        {renderInline(block.text, byId, onPick)}
      </p>
    );
  });

  return <div className="facilitate-content">{rendered}</div>;
}
