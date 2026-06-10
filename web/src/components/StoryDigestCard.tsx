import { useState } from "react";
import { renderMathText } from "../lib/renderRichText";
import type { StoryDigest, StoryCitation } from "../types";

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
          <div className="story-take__rail">
            <div className="story-take__num">{i + 1}</div>
            {i < digest.takes.length - 1 && <div className="story-take__line" />}
          </div>
          <div className="story-take__body">
            <h3 className="story-take__heading">{renderMathText(t.heading)}</h3>
            <div className="story-take__story">{renderMathText(t.story)}</div>
            {t.items.length > 0 && (
              <div className="curiosity-box">
                <button type="button" className="curiosity-box__toggle" aria-expanded={open.has(i)} onClick={() => toggle(i)}>
                  {open.has(i) ? "▾" : "▸"} Curiosity box ({t.items.length})
                </button>
                {open.has(i) && (
                  <ul className="curiosity-box__items">
                    {t.items.map((it, j) => (
                      <li key={j} className="curiosity-item">
                        <span className="curiosity-item__subject">{renderMathText(it.subject)}</span>
                        <div className="curiosity-item__body">{renderMathText(it.body)}</div>
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
