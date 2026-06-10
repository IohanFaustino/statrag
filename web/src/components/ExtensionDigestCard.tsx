import React, { useState } from "react";
import StructuredErrorBoundary from "./StructuredErrorBoundary";
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
 * Renders digest text (point titles, curated text, footnote bodies): splits on
 * $$...$$ (display) and $...$ (inline), renders via KaTeX. Plain text segments
 * rendered as-is. Does NOT apply [N] citation logic — footnotes use the marker
 * field.
 */
function renderMathText(body: string): React.ReactNode {
  if (!body) return null;
  const parts: React.ReactNode[] = [];
  const segments = body.split(/((?:\$\$[\s\S]*?\$\$|\$[^$\n]+\$))/g);
  segments.forEach((seg, i) => {
    if (seg.startsWith("$$") && seg.endsWith("$$") && seg.length > 4) {
      parts.push(<MathBlock key={i} tex={seg.slice(2, -2)} />);
    } else if (seg.startsWith("$") && seg.endsWith("$") && seg.length > 2) {
      parts.push(<MathInline key={i} tex={seg.slice(1, -1)} />);
    } else {
      parts.push(<span key={i}>{seg}</span>);
    }
  });
  return <>{parts}</>;
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
                      {renderMathText(fn.body)}
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
  return (
    <StructuredErrorBoundary>
      <ExtensionDigestCardInner {...props} />
    </StructuredErrorBoundary>
  );
}
