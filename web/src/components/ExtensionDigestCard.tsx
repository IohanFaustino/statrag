import React, { useState } from "react";
import { MathInline, MathBlock } from "./Math";

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

// ─── Footnote body renderer ───────────────────────────────────────────────────

/**
 * Persisted digests (and some model outputs) use LaTeX delimiters the split
 * regex can't see: \(…\), \[…\], and display blocks written as a lone `$` on
 * its own line. Normalize all of them to $…$ / $$…$$ before splitting.
 */
function normalizeMathDelimiters(body: string): string {
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
function renderInlineMarkdown(text: string, keyPrefix: string): React.ReactNode[] {
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
function renderMathText(body: string): React.ReactNode {
  if (!body) return null;
  const parts: React.ReactNode[] = [];
  const segments = normalizeMathDelimiters(body).split(/((?:\$\$[\s\S]*?\$\$|\$[^$\n]+\$))/g);
  segments.forEach((seg, i) => {
    if (seg.startsWith("$$") && seg.endsWith("$$") && seg.length > 4) {
      parts.push(<MathBlock key={i} tex={seg.slice(2, -2)} />);
    } else if (seg.startsWith("$") && seg.endsWith("$") && seg.length > 2) {
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

/**
 * Renders a footnote body: strips the leading duplicated marker first, then
 * delegates to renderMathText for math + markdown processing.
 */
function renderFootnoteBody(body: string, marker: string): React.ReactNode {
  return renderMathText(stripLeadingMarker(body, marker));
}

// ─── Source display ───────────────────────────────────────────────────────────

const MAX_SOURCE_CHARS = 40;

function truncateSource(source: string): string {
  if (source.length <= MAX_SOURCE_CHARS) return source;
  return source.slice(0, MAX_SOURCE_CHARS) + "…";
}

function FootnoteSource({ fn }: { fn: ExtensionFootnote }) {
  if (fn.kind === "wikipedia") {
    return (
      <span className="extension-footnote__source">
        (
        <a
          href={fn.source}
          target="_blank"
          rel="noopener noreferrer"
          className="extension-footnote__wiki-link"
        >
          Wikipedia
        </a>
        )
      </span>
    );
  }
  return (
    <span className="extension-footnote__source">
      ({truncateSource(fn.source)} · corpus)
    </span>
  );
}

// ─── Download helper ──────────────────────────────────────────────────────────

async function downloadZip(
  digest: ExtensionDigest,
  setLoading: (v: boolean) => void,
  setError: (v: string | null) => void,
): Promise<void> {
  setLoading(true);
  setError(null);
  try {
    const res = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(digest),
    });
    if (!res.ok) {
      setError(`Export failed (${res.status})`);
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${digest.book}-${digest.chapter}-extended.zip`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch {
    setError("Export failed — network error");
  } finally {
    setLoading(false);
  }
}

// ─── Component ────────────────────────────────────────────────────────────────

interface Props {
  digest: ExtensionDigest;
  pendingPoints?: string[];
}

function ExtensionDigestCardInner({ digest }: Props) {
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

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
          disabled={isDownloading}
          onClick={() => downloadZip(digest, setIsDownloading, setDownloadError)}
        >
          {isDownloading ? "Downloading…" : "Download ZIP"}
        </button>
        {downloadError && (
          <span className="extension-card__download-error" role="alert">
            {downloadError}
          </span>
        )}
      </div>

      <div className="extension-card__points">
        {digest.points.map((pt, i) => (
          <section key={i} className="extension-point">
            <h3 className="extension-point__title">{renderMathText(pt.title)}</h3>
            <div className="extension-point__body">{renderMathText(pt.curated_text)}</div>

            {pt.footnotes.length > 0 && (
              <ul className="extension-point__footnotes">
                {pt.footnotes.map((fn, j) => (
                  <li key={j} className="extension-footnote">
                    <sup className="extension-footnote__marker">{fn.marker}</sup>
                    <span className="extension-footnote__body">
                      {renderFootnoteBody(fn.body, fn.marker)}
                    </span>
                    <FootnoteSource fn={fn} />
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
              <li key={i}>{renderMathText(gap)}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function ExtensionDigestCard(props: Props) {
  return <ExtensionDigestCardInner {...props} />;
}
