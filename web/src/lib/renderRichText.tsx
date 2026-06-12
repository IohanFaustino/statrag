import React from "react";
import { MathInline, MathBlock } from "../components/Math";

/**
 * Persisted digests (and some model outputs) use LaTeX delimiters the split
 * regex can't see: \(…\), \[…\], and display blocks written as a lone `$` on
 * its own line. Normalize all of them to $…$ / $$…$$ before splitting.
 */
export function normalizeMathDelimiters(body: string): string {
  return body
    .replace(/\\\[([\s\S]*?)\\\]/g, (_m, tex) => `$$${tex}$$`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_m, tex) => `$${tex}$`)
    .replace(
      /(^|\n)[ \t]*\$[ \t]*\n([\s\S]*?)\n[ \t]*\$[ \t]*(?=\n|$)/g,
      (_m, pre, tex) => `${pre}$$${tex}$$`,
    );
}

/**
 * Strips a leading duplicated marker from a footnote body.
 * E.g. body = "2. Some text" with marker = "2" → "Some text".
 * Supports "marker. " and "marker) " forms.
 * Only strips when the body actually starts with the exact marker.
 */
export function stripLeadingMarker(body: string, marker: string): string {
  const escaped = marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  // [.)] = separator class (dot or paren); [\s]+ = required whitespace after it
  return body.replace(new RegExp(`^${escaped}[.)][\\s]+`), "");
}

/**
 * Renders inline markdown (bold, italic) in a plain-text segment.
 * Strategy:
 *   - **word** → <strong>
 *   - *word* (tight, no spaces at boundary) → <em>
 *     NOTE: bare `a * b` (spaces around *) is NOT treated as italic, so
 *     multiplication-like usage stays literal.
 *   - [^digits] → removed (stray footnote reference markers)
 *
 * Returns an array of ReactNode (mixed strings + elements) suitable for
 * insertion into a larger parts array.
 */
export function renderInlineMarkdown(text: string, keyPrefix: string): React.ReactNode[] {
  // First strip [^n] markers
  const stripped = text.replace(/\[\^\d+\]/g, "");

  // Split on **…** and *word* (tight italic: no space at boundaries, and the
  // opening * must NOT be preceded by alphanumeric and closing * must NOT be
  // followed by alphanumeric — prevents mid-word matches like x*y*z).
  // Order matters: match **…** before *…* to avoid partial matches.
  const mdParts = stripped.split(/(\*\*[^*]+\*\*|(?<![a-zA-Z0-9])\*\S[^*]*\S\*(?![a-zA-Z0-9])|(?<![a-zA-Z0-9])\*\S\*(?![a-zA-Z0-9]))/g);

  return mdParts.map((part, j): React.ReactNode => {
    const k = `${keyPrefix}-md${j}`;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={k}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={k}>{part.slice(1, -1)}</em>;
    }
    return part; // plain string (React renders strings fine in arrays)
  });
}

/**
 * Renders digest text (point titles, curated text, footnote bodies): splits on
 * $$...$$ (display) and $...$ (inline), renders via KaTeX. Plain text segments
 * get lightweight markdown processing (**bold**, *italic*) and [^n] stripping.
 * Does NOT apply [N] citation logic — footnotes use the marker field.
 */
/** A `$…$` span that contains several natural-language words is the model
 *  stuffing prose into math delimiters, not real math — render it as text. */
function looksLikeProse(inner: string): boolean {
  // Strip LaTeX command names (e.g. \mathrm, \delta) before counting so
  // legit math like \mathrm{Var}(X)/\delta^2 is not misread as prose.
  const words = inner.replace(/\\[a-zA-Z]+/g, " ").match(/\b[a-zA-Z]{2,}\b/g) || [];
  return words.length >= 3;
}

export function renderMathText(body: string): React.ReactNode {
  if (!body) return null;
  const normalized = normalizeMathDelimiters(body);
  // Guard: if single-`$` delimiters are unbalanced (odd count, ignoring
  // escaped `\$`), the paragraph is malformed — never feed a half-open span
  // to KaTeX (that produces glommed-glyph soup). Render it as plain markdown.
  const dollars = (normalized.match(/(?<!\\)\$/g) || []).length;
  if (dollars % 2 !== 0) {
    return <span>{renderInlineMarkdown(normalized, "0")}</span>;
  }
  const parts: React.ReactNode[] = [];
  const segments = normalized.split(/((?:\$\$[\s\S]*?\$\$|\$[^$\n]+\$))/g);
  segments.forEach((seg, i) => {
    if (seg.startsWith("$$") && seg.endsWith("$$") && seg.length > 4) {
      parts.push(<MathBlock key={i} tex={seg.slice(2, -2)} />);
    } else if (seg.startsWith("$") && seg.endsWith("$") && seg.length > 2 && !looksLikeProse(seg.slice(1, -1))) {
      parts.push(<MathInline key={i} tex={seg.slice(1, -1)} />);
    } else {
      // Plain text segment: apply inline markdown + [^n] stripping.
      // Always wrapped in a span so inline nodes have a stable React key root.
      const inlineNodes = renderInlineMarkdown(seg, String(i));
      parts.push(<span key={i}>{inlineNodes}</span>);
    }
  });
  return <>{parts}</>;
}
