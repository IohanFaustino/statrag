import React, { useState } from "react";
import type { Source, Figure, RetrievalMetadata } from "../types";
import type { FiguresMeta } from "../state/chat";
import { IconChevron, IconChevronRight, IconChevronLeft } from "./Icons";

interface ContextPanelProps {
  sources: Source[];
  figures: Figure[];
  figuresMeta?: FiguresMeta;
  metadata?: RetrievalMetadata;
  collapsed: boolean;
  onToggle(): void;
  onSourceClick(s: Source): void;
}

const FIGURES_META_LABEL: Record<FiguresMeta["status"], string> = {
  ok: "",
  disabled: "",
  no_sources: "No sources retrieved",
  no_candidates: "No figure candidates",
  all_rejected: "All candidates rejected by vision judge",
  error: "Image branch errored",
};

function ScoreBadge({ score }: { score: number }) {
  const tone = score >= 0.8 ? "hi" : score >= 0.6 ? "mid" : "low";
  return (
    <span className={`score-badge score-badge--${tone}`}>
      {score.toFixed(2)}
    </span>
  );
}

function SourceCard({
  src,
  onOpen,
}: {
  src: Source;
  onOpen?: (s: Source) => void;
}) {
  const bookKey = (src.book || "").toLowerCase();
  return (
    <button
      className="source-card"
      type="button"
      onClick={() => onOpen?.(src)}
    >
      <div className="source-card__hd">
        <span className={`book-tag book-tag--${bookKey}`}>
          <span className={`dot dot--${bookKey}`} />
          {src.book === "HANSEN" ? "Hansen" : (src.book || "?")}
        </span>
        <span className="source-card__hd-right">
          <span className="source-card__rank">#{src.rank}</span>
          <ScoreBadge score={src.score} />
        </span>
      </div>
      <div className="source-card__path">
        {src.chapter} · {src.section}
      </div>
      <div className="source-card__title">{src.title}</div>
      <div className="source-card__excerpt">"{src.excerpt}"</div>
    </button>
  );
}

function FigureCard({ fig }: { fig: Figure }) {
  return (
    <button className="figure-card" type="button">
      <div className="figure-card__hd">
        <span className="book-tag book-tag--figure">
          <span className="dot dot--figure" /> Figure
        </span>
        <span className="figure-card__path">
          {fig.book} · {fig.chapter} · {fig.ref}
        </span>
      </div>
      <div className="figure-card__thumb">
        {fig.chart && (fig.chart.startsWith("/") || fig.chart.startsWith("http")) ? (
          <img
            src={fig.chart}
            alt={fig.caption}
            loading="lazy"
            style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <svg viewBox="0 0 80 60" width="80" height="60" aria-label={fig.caption}>
            <rect x="1" y="1" width="78" height="58" fill="none" stroke="rgba(229,72,77,0.2)" strokeWidth="1" />
            <text x="40" y="34" textAnchor="middle" fill="rgba(229,72,77,0.4)" fontSize="9" fontFamily="IBM Plex Mono, monospace">
              {fig.chart || "no preview"}
            </text>
          </svg>
        )}
      </div>
      <div className="figure-card__caption">"{fig.caption}"</div>
    </button>
  );
}

function RetrievalAccordion({ metadata }: { metadata: RetrievalMetadata }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="ctx-section">
      <button
        className="ctx-acc"
        onClick={() => setOpen((o) => !o)}
        type="button"
        aria-expanded={open}
      >
        <span
          className={"ctx-acc__caret" + (open ? " is-open" : "")}
          aria-hidden="true"
        >
          <IconChevron />
        </span>
        <span className="ctx-section__label">Retrieval</span>
      </button>
      {open && (
        <div className="ctx-meta">
          <div className="ctx-meta__row">
            <span>Query (rewritten)</span>
            <span className="ctx-meta__val">"{metadata.rewrittenQuery}"</span>
          </div>
          <div className="ctx-meta__row">
            <span>Embedding</span>
            <span className="ctx-meta__val">{metadata.embedding}</span>
          </div>
          <div className="ctx-meta__row">
            <span>Retrieval</span>
            <span className="ctx-meta__val">{metadata.retrievalMs}ms</span>
          </div>
          <div className="ctx-meta__row">
            <span>Mode</span>
            <span className="ctx-meta__val">{metadata.mode}</span>
          </div>
          <div className="ctx-meta__row">
            <span>top-K</span>
            <span className="ctx-meta__val">{metadata.topK}</span>
          </div>
          <div className="ctx-meta__row">
            <span>score ≥</span>
            <span className="ctx-meta__val">{metadata.scoreThreshold}</span>
          </div>
          <div className="ctx-meta__row">
            <span>Filter</span>
            <span className="ctx-meta__val">{metadata.filter}</span>
          </div>
          <div className="ctx-meta__row">
            <span>Collections</span>
            <span className="ctx-meta__val">
              {metadata.collections.join(", ")}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ContextPanel({
  sources,
  figures,
  figuresMeta,
  metadata,
  collapsed,
  onToggle,
  onSourceClick,
}: ContextPanelProps) {
  const showMetaChip =
    !!figuresMeta &&
    figuresMeta.status !== "ok" &&
    figuresMeta.status !== "disabled" &&
    figures.length === 0;
  if (collapsed) {
    return (
      <button
        className="ctx-rail"
        onClick={onToggle}
        type="button"
        title="Show sources"
        aria-label="Show sources panel"
      >
        <IconChevronLeft />
        <span className="ctx-rail__label">SOURCES</span>
        <span className="ctx-rail__count">{sources.length}</span>
      </button>
    );
  }

  return (
    <aside className="ctx-panel">
      <button
        className="ctx-panel__collapse"
        onClick={onToggle}
        type="button"
        title="Hide panel"
        aria-label="Hide sources panel"
      >
        <IconChevronRight />
      </button>

      <div className="ctx-panel__scroll">
        {sources.length > 0 && (
          <div className="ctx-section">
            <div className="ctx-section__hd">
              <span className="ctx-section__label">Sources</span>
              <span className="ctx-section__count">({sources.length})</span>
            </div>
            <div className="ctx-section__list">
              {sources.map((s) => (
                <SourceCard key={s.rank} src={s} onOpen={onSourceClick} />
              ))}
            </div>
          </div>
        )}

        {figures.length > 0 && (
          <div className="ctx-section">
            <div className="ctx-section__hd">
              <span className="ctx-section__label">Figures</span>
              <span className="ctx-section__count">({figures.length})</span>
            </div>
            <div className="ctx-section__list">
              {figures.map((f) => (
                <FigureCard key={f.ref} fig={f} />
              ))}
            </div>
          </div>
        )}

        {showMetaChip && figuresMeta && (
          <div className="ctx-section">
            <div className="ctx-section__hd">
              <span className="ctx-section__label">Figures</span>
              <span className="ctx-section__count">(0)</span>
            </div>
            <div
              className="ctx-meta-chip"
              title={figuresMeta.reason}
              style={{
                fontSize: "0.75em",
                opacity: 0.6,
                padding: "0.4em 0.6em",
                border: "1px dashed currentColor",
                borderRadius: 4,
                margin: "0.4em 0",
                lineHeight: 1.4,
              }}
            >
              {FIGURES_META_LABEL[figuresMeta.status] || figuresMeta.status}
              {figuresMeta.candidateCount > 0 && (
                <> · {figuresMeta.candidateCount} candidate
                  {figuresMeta.candidateCount === 1 ? "" : "s"}</>
              )}
            </div>
          </div>
        )}

        {metadata && <RetrievalAccordion metadata={metadata} />}
      </div>
    </aside>
  );
}
