import React, { useState } from "react";
import type { Book } from "../../types";
import FocusModal from "./FocusModal";

// Slugs with extracted PDF front pages in /public/covers/
const PHOTO_COVERS = new Set([
  "atwan", "baltagi", "chollet", "das", "gujarati", "hansen", "hernan",
  "islp", "lis_rosser", "mcneil", "moss", "neal", "pearl", "peck",
  "pesaran", "peters", "wooldridge",
]);

// ─── Book covers (stylised SVG with photo override) ───────────────────────────

function BookCover({ book, size = "lg" }: { book: Book; size?: "sm" | "lg" }) {
  const w = size === "sm" ? 56 : 92;
  const h = size === "sm" ? 78 : 132;
  const dims = `0 0 ${w} ${h}`;

  // Use real front page if available
  if (PHOTO_COVERS.has(book.id)) {
    return (
      <img
        className="book-cover book-cover--img"
        src={`/covers/${book.id}.jpg`}
        alt={book.title}
        width={w}
        height={h}
        loading="lazy"
        decoding="async"
      />
    );
  }

  if (book.cover === "islp") {
    return (
      <svg viewBox={dims} width={w} height={h} className="book-cover" aria-label={book.title}>
        <defs>
          <linearGradient id="islp-g" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#1f4332" />
            <stop offset="1" stopColor="#0c2a1f" />
          </linearGradient>
        </defs>
        <rect x="0" y="0" width={w} height={h} fill="url(#islp-g)" />
        <rect x="0" y="0" width="3" height={h} fill="#0a1f17" />
        <rect x={w * 0.18} y={h * 0.10} width={w * 0.64} height={h * 0.46} fill="#0a1f17" opacity="0.5" rx="1" />
        <g fill="#7EC8A4">
          {([[0.30, 0.20], [0.42, 0.28], [0.55, 0.22], [0.68, 0.34], [0.78, 0.30], [0.36, 0.36], [0.50, 0.42], [0.62, 0.40], [0.74, 0.46], [0.45, 0.50]] as [number, number][]).map((p, i) => (
            <circle key={i} cx={w * p[0]} cy={h * p[1]} r={size === "sm" ? 1.2 : 2} opacity={0.6 + (i % 3) * 0.13} />
          ))}
          <path d={`M${w * 0.22} ${h * 0.50} Q ${w * 0.5} ${h * 0.18} ${w * 0.80} ${h * 0.20}`} fill="none" stroke="#7EC8A4" strokeWidth={size === "sm" ? 0.8 : 1.2} opacity="0.7" />
        </g>
        <text x={w / 2} y={h * 0.70} fill="#E8ECF0" fontSize={size === "sm" ? 7 : 11} fontFamily="serif" fontWeight="600" textAnchor="middle" letterSpacing="0.04em">ISLP</text>
        <text x={w / 2} y={h * 0.78} fill="#7EC8A4" fontSize={size === "sm" ? 4 : 6} fontFamily="serif" textAnchor="middle" opacity="0.85">with Python</text>
        <text x={w / 2} y={h * 0.92} fill="#E8ECF0" fontSize={size === "sm" ? 3.5 : 5} fontFamily="monospace" textAnchor="middle" opacity="0.7">JAMES · WITTEN · HASTIE</text>
      </svg>
    );
  }

  if (book.cover === "hansen") {
    return (
      <svg viewBox={dims} width={w} height={h} className="book-cover" aria-label={book.title}>
        <defs>
          <linearGradient id="hans-g" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#3a2517" />
            <stop offset="1" stopColor="#1d1108" />
          </linearGradient>
        </defs>
        <rect x="0" y="0" width={w} height={h} fill="url(#hans-g)" />
        <rect x="0" y="0" width="3" height={h} fill="#13090a" />
        <rect x={w * 0.10} y={h * 0.06} width={w * 0.80} height={h * 0.86} fill="none" stroke="#E8A87C" strokeWidth="0.6" opacity="0.4" />
        <rect x={w * 0.13} y={h * 0.09} width={w * 0.74} height={h * 0.80} fill="none" stroke="#E8A87C" strokeWidth="0.3" opacity="0.3" />
        <text x={w / 2} y={h * 0.32} fill="#E8A87C" fontSize={size === "sm" ? 5 : 7} fontFamily="serif" textAnchor="middle" letterSpacing="0.25em" opacity="0.9">ECONO-</text>
        <text x={w / 2} y={h * 0.42} fill="#E8A87C" fontSize={size === "sm" ? 5 : 7} fontFamily="serif" textAnchor="middle" letterSpacing="0.25em" opacity="0.9">METRICS</text>
        <line x1={w * 0.30} y1={h * 0.48} x2={w * 0.70} y2={h * 0.48} stroke="#E8A87C" strokeWidth="0.4" opacity="0.5" />
        <text x={w / 2} y={h * 0.58} fill="#E8ECF0" fontSize={size === "sm" ? 4 : 5.5} fontFamily="serif" fontStyle="italic" textAnchor="middle" opacity="0.6">y = Xβ + ε</text>
        <text x={w / 2} y={h * 0.80} fill="#E8ECF0" fontSize={size === "sm" ? 3.5 : 5} fontFamily="serif" textAnchor="middle" letterSpacing="0.04em">B. E. HANSEN</text>
        <text x={w / 2} y={h * 0.92} fill="#E8A87C" fontSize={size === "sm" ? 2.8 : 4} fontFamily="monospace" textAnchor="middle" opacity="0.6">PRINCETON · 2022</text>
      </svg>
    );
  }

  if (book.cover === "esl") {
    return (
      <svg viewBox={dims} width={w} height={h} className="book-cover" aria-label={book.title}>
        <rect x="0" y="0" width={w} height={h} fill="#1a1530" />
        <rect x="0" y="0" width="3" height={h} fill="#0c0820" />
        <g stroke="#9B8FCC" strokeWidth={size === "sm" ? 0.5 : 0.8} fill="none" opacity="0.85">
          <path d={`M${w * 0.20} ${h * 0.55} V ${h * 0.30} H ${w * 0.80} V ${h * 0.55}`} />
          <path d={`M${w * 0.30} ${h * 0.55} V ${h * 0.40} H ${w * 0.50} V ${h * 0.55}`} />
          <path d={`M${w * 0.60} ${h * 0.55} V ${h * 0.40} H ${w * 0.70} V ${h * 0.55}`} />
          {([0.20, 0.30, 0.50, 0.60, 0.70, 0.80] as number[]).map((x, i) => (
            <circle key={i} cx={w * x} cy={h * 0.56} r={size === "sm" ? 1 : 1.4} fill="#9B8FCC" />
          ))}
        </g>
        <text x={w / 2} y={h * 0.78} fill="#E8ECF0" fontSize={size === "sm" ? 6 : 9} fontFamily="serif" fontWeight="500" textAnchor="middle">ESL</text>
        <text x={w / 2} y={h * 0.88} fill="#9B8FCC" fontSize={size === "sm" ? 3.5 : 5} fontFamily="monospace" textAnchor="middle" opacity="0.7">HASTIE et al.</text>
      </svg>
    );
  }

  if (book.cover === "wooldridge") {
    return (
      <svg viewBox={dims} width={w} height={h} className="book-cover" aria-label={book.title}>
        <rect x="0" y="0" width={w} height={h} fill="#0e2438" />
        <rect x="0" y="0" width="3" height={h} fill="#061626" />
        <g stroke="#4F9CF9" strokeWidth="0.4" opacity="0.5">
          {([0, 1, 2, 3, 4] as number[]).map((i) => (
            <line key={`h${i}`} x1={w * 0.15} y1={h * (0.18 + i * 0.08)} x2={w * 0.85} y2={h * (0.18 + i * 0.08)} />
          ))}
          {([0, 1, 2, 3, 4, 5, 6] as number[]).map((i) => (
            <line key={`v${i}`} x1={w * (0.15 + i * 0.11)} y1={h * 0.18} x2={w * (0.15 + i * 0.11)} y2={h * 0.5} />
          ))}
        </g>
        <g fill="#4F9CF9">
          {([[0.20, 0.22], [0.31, 0.30], [0.42, 0.26], [0.53, 0.34], [0.64, 0.38], [0.75, 0.42]] as [number, number][]).map((p, i) => (
            <circle key={i} cx={w * p[0]} cy={h * p[1]} r={size === "sm" ? 0.9 : 1.4} />
          ))}
        </g>
        <text x={w / 2} y={h * 0.70} fill="#E8ECF0" fontSize={size === "sm" ? 5 : 7} fontFamily="serif" textAnchor="middle" letterSpacing="0.1em">ECONOMETRIC</text>
        <text x={w / 2} y={h * 0.78} fill="#E8ECF0" fontSize={size === "sm" ? 5 : 7} fontFamily="serif" textAnchor="middle" letterSpacing="0.1em">ANALYSIS</text>
        <text x={w / 2} y={h * 0.91} fill="#4F9CF9" fontSize={size === "sm" ? 3.5 : 5} fontFamily="monospace" textAnchor="middle" opacity="0.8">WOOLDRIDGE</text>
      </svg>
    );
  }

  // Generic fallback cover — surname on paper with a thin colored spine
  // (avoids saturated blocks that read as broken images on light cards).
  return (
    <div
      className="book-cover"
      data-cover={book.cover}
      style={{
        width: w,
        height: h,
        background: "var(--bg-secondary)",
        borderLeft: `3px solid ${book.color ?? "var(--border-default)"}`,
        boxShadow: "inset 0 0 0 1px var(--border-subtle)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        padding: "0 4px",
        fontSize: size === "sm" ? 8 : 12,
        color: "var(--text-secondary)",
        fontFamily: "var(--font-serif)",
        fontWeight: 600,
        letterSpacing: "0.02em",
      }}
      aria-label={book.title}
    >
      {book.short}
    </div>
  );
}

// ─── Book card ────────────────────────────────────────────────────────────────

function BookCard({
  book,
  onToggle,
  compact = false,
}: {
  book: Book;
  onToggle(id: string): void;
  compact?: boolean;
}) {
  const isIndexed = book.indexed !== false;
  return (
    <article
      className={
        "book-card" +
        (book.selected ? " is-selected" : "") +
        (!isIndexed ? " is-pending" : "") +
        (compact ? " is-compact" : "")
      }
    >
      <div className="book-card__cover">
        <BookCover book={book} size={compact ? "sm" : "lg"} />
        <span
          className="book-card__pin"
          style={{ background: book.color, boxShadow: `0 0 8px ${book.color}` }}
          aria-hidden="true"
        />
      </div>
      <div className="book-card__body">
        <div className="book-card__short">{book.short}</div>
        <h3 className="book-card__title">{book.title}</h3>
        {!compact && <div className="book-card__sub">{book.subtitle}</div>}
        <div className="book-card__authors">{book.authors}</div>
        <div className="book-card__edition">{book.edition}</div>
        {!compact && (
          <div className="book-card__stats">
            <div className="book-stat">
              <span>Chunks</span>
              <b>{book.chunks.toLocaleString()}</b>
            </div>
            <div className="book-stat">
              <span>Figures</span>
              <b>{book.figures}</b>
            </div>
            <div className="book-stat">
              <span>Chapters</span>
              <b>{book.chapters}</b>
            </div>
          </div>
        )}
        {!compact && <p className="book-card__desc">{book.description}</p>}
        <div className="book-card__foot">
          <span className="book-card__coll">
            <code>{book.collection}</code>
          </span>
          {!isIndexed ? (
            <button className="book-card__btn book-card__btn--idx" type="button">
              + Index
            </button>
          ) : (
            <button
              className={"book-card__toggle" + (book.selected ? " is-on" : "")}
              type="button"
              aria-pressed={book.selected}
              onClick={() => onToggle(book.id)}
            >
              <span className="book-card__toggle-knob" />
              <span className="book-card__toggle-lbl">
                {book.selected ? "Included" : "Excluded"}
              </span>
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

// ─── Book modal ───────────────────────────────────────────────────────────────

interface BookModalProps {
  open: boolean;
  onClose(): void;
  books: Book[];
  onToggle(id: string): void;
}

const FIELD_LABEL: Record<string, string> = {
  econometrics: "Econometrics",
  ml_dp: "ML & Deep Learning",
  introduction: "Introduction",
  causal_inference: "Causal Inference",
  math: "Math",
  risk: "Risk",
};

function fieldLabel(field: string): string {
  return FIELD_LABEL[field] ?? field.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function BookModal({ open, onClose, books, onToggle }: BookModalProps) {
  const indexed = books.filter((b) => b.indexed !== false);
  const selected = books.filter((b) => b.selected);

  // Unique fields (collections)
  const fields = Array.from(new Set(indexed.map((b) => b.field))).sort();

  const [activeField, setActiveField] = useState<string>("ALL");

  // Apply collection filter
  const visibleBooks =
    activeField === "ALL" ? indexed : indexed.filter((b) => b.field === activeField);

  // Per-field counts
  const fieldCounts = fields.reduce<Record<string, { total: number; on: number }>>(
    (acc, f) => {
      const inField = indexed.filter((b) => b.field === f);
      acc[f] = { total: inField.length, on: inField.filter((b) => b.selected).length };
      return acc;
    },
    {},
  );

  // Bulk toggle for collection
  function toggleCollection(field: string) {
    const inField = indexed.filter((b) => b.field === field);
    const allOn = inField.every((b) => b.selected);
    inField.forEach((b) => {
      if (allOn === b.selected) onToggle(b.id);
    });
  }

  return (
    <FocusModal open={open} onClose={onClose} size="lg" labelledBy="bm-title">
      <header className="fm__hd bm-hd">
        <div className="bm-tile">
          <h2 id="bm-title" className="bm-tile__title">Library</h2>
          <div className="bm-tile__meta">
            <span className="bm-tile__count">{selected.length}</span>
            <span className="bm-tile__sub">/ {indexed.length} books selected · {fields.length} collections</span>
          </div>
        </div>
        <button className="fm__close" type="button" onClick={onClose} aria-label="Close">
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
            <path d="m4 4 8 8M12 4l-8 8" />
          </svg>
        </button>
      </header>

      <div className="bm-chip-row">
        <div className="bm-chip-row__chips">
          <button
            className={"bm-chip bm-chip--all" + (activeField === "ALL" ? " is-on" : "")}
            type="button"
            onClick={() => setActiveField("ALL")}
            aria-pressed={activeField === "ALL"}
          >
            <span className="bm-chip__name">All</span>
            <span className="bm-chip__count">{indexed.length}</span>
          </button>
          {fields.map((f) => {
            const c = fieldCounts[f];
            const isActive = activeField === f;
            return (
              <button
                key={f}
                className={"bm-chip" + (isActive ? " is-on" : "")}
                type="button"
                onClick={() => setActiveField(f)}
                aria-pressed={isActive}
                title={`${c.on}/${c.total} selected — click to filter, shift-click to toggle all`}
                onContextMenu={(e) => {
                  e.preventDefault();
                  toggleCollection(f);
                }}
              >
                <span className="bm-chip__name">{fieldLabel(f)}</span>
                <span className="bm-chip__count">
                  {c.on}/{c.total}
                </span>
              </button>
            );
          })}
        </div>
        {activeField !== "ALL" && (
          <button
            className="bm-chip-row__bulk"
            type="button"
            onClick={() => toggleCollection(activeField)}
          >
            Toggle all in {fieldLabel(activeField)}
          </button>
        )}
      </div>

      <div className="fm__body">
        {visibleBooks.length > 0 ? (
          <div className="book-grid">
            {visibleBooks.map((b) => (
              <BookCard key={b.id} book={b} onToggle={onToggle} />
            ))}
          </div>
        ) : (
          <div className="bm-empty">
            <div className="bm-empty__glyph" aria-hidden="true">∅</div>
            <div className="bm-empty__title">No books in this collection</div>
            <p className="bm-empty__text">Pick another collection above.</p>
          </div>
        )}
      </div>

      <footer className="fm__ft">
        <span className="fm__ft-hint">⌘+B open · Esc close · right-click chip to toggle collection</span>
        <button className="btn btn--primary" type="button" onClick={onClose}>
          Apply
        </button>
      </footer>
    </FocusModal>
  );
}
