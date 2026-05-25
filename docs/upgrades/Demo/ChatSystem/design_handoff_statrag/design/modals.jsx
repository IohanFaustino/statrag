// Focus modals: BookModal + SourceModal + generic FocusModal wrapper
const { useState: mUs, useEffect: mEf, useRef: mRf } = React;

// ─── Generic focus modal ─────────────────────────────────────────────────────
function FocusModal({ open, onClose, children, size = "default", labelledBy }) {
  mEf(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fm" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby={labelledBy}>
      <div className={"fm__panel fm__panel--" + size} onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}

// ─── Book covers (stylised SVG) ──────────────────────────────────────────────
function BookCover({ book, size = "lg" }) {
  const w = size === "sm" ? 56 : 92;
  const h = size === "sm" ? 78 : 132;
  const dims = `0 0 ${w} ${h}`;
  if (book.cover === "islp") {
    return (
      <svg viewBox={dims} width={w} height={h} className="book-cover" aria-label={book.title}>
        <defs>
          <linearGradient id="islp-g" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#1f4332"/><stop offset="1" stopColor="#0c2a1f"/>
          </linearGradient>
        </defs>
        <rect x="0" y="0" width={w} height={h} fill="url(#islp-g)"/>
        <rect x="0" y="0" width="3" height={h} fill="#0a1f17"/>
        <rect x={w*0.18} y={h*0.10} width={w*0.64} height={h*0.46} fill="#0a1f17" opacity="0.5" rx="1"/>
        {/* Stylized scatter cloud */}
        <g fill="#7EC8A4">
          {[[0.30,0.20],[0.42,0.28],[0.55,0.22],[0.68,0.34],[0.78,0.30],[0.36,0.36],[0.50,0.42],[0.62,0.40],[0.74,0.46],[0.45,0.50]].map((p,i) => (
            <circle key={i} cx={w*p[0]} cy={h*p[1]} r={size === "sm" ? 1.2 : 2} opacity={0.6 + (i%3)*0.13}/>
          ))}
          <path d={`M${w*0.22} ${h*0.50} Q ${w*0.5} ${h*0.18} ${w*0.80} ${h*0.20}`} fill="none" stroke="#7EC8A4" strokeWidth={size==="sm"?0.8:1.2} opacity="0.7"/>
        </g>
        <text x={w/2} y={h*0.70} fill="#E8ECF0" fontSize={size==="sm"?7:11} fontFamily="serif" fontWeight="600" textAnchor="middle" letterSpacing="0.04em">ISLP</text>
        <text x={w/2} y={h*0.78} fill="#7EC8A4" fontSize={size==="sm"?4:6} fontFamily="serif" textAnchor="middle" opacity="0.85">with Python</text>
        <text x={w/2} y={h*0.92} fill="#E8ECF0" fontSize={size==="sm"?3.5:5} fontFamily="monospace" textAnchor="middle" opacity="0.7">JAMES · WITTEN · HASTIE</text>
      </svg>
    );
  }
  if (book.cover === "hansen") {
    return (
      <svg viewBox={dims} width={w} height={h} className="book-cover" aria-label={book.title}>
        <defs>
          <linearGradient id="hans-g" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#3a2517"/><stop offset="1" stopColor="#1d1108"/>
          </linearGradient>
        </defs>
        <rect x="0" y="0" width={w} height={h} fill="url(#hans-g)"/>
        <rect x="0" y="0" width="3" height={h} fill="#13090a"/>
        <rect x={w*0.10} y={h*0.06} width={w*0.80} height={h*0.86} fill="none" stroke="#E8A87C" strokeWidth="0.6" opacity="0.4"/>
        <rect x={w*0.13} y={h*0.09} width={w*0.74} height={h*0.80} fill="none" stroke="#E8A87C" strokeWidth="0.3" opacity="0.3"/>
        <text x={w/2} y={h*0.32} fill="#E8A87C" fontSize={size==="sm"?5:7} fontFamily="serif" textAnchor="middle" letterSpacing="0.25em" opacity="0.9">ECONO-</text>
        <text x={w/2} y={h*0.42} fill="#E8A87C" fontSize={size==="sm"?5:7} fontFamily="serif" textAnchor="middle" letterSpacing="0.25em" opacity="0.9">METRICS</text>
        <line x1={w*0.30} y1={h*0.48} x2={w*0.70} y2={h*0.48} stroke="#E8A87C" strokeWidth="0.4" opacity="0.5"/>
        {/* equation glyphs */}
        <text x={w/2} y={h*0.58} fill="#E8ECF0" fontSize={size==="sm"?4:5.5} fontFamily="serif" fontStyle="italic" textAnchor="middle" opacity="0.6">y = Xβ + ε</text>
        <text x={w/2} y={h*0.80} fill="#E8ECF0" fontSize={size==="sm"?3.5:5} fontFamily="serif" textAnchor="middle" letterSpacing="0.04em">B. E. HANSEN</text>
        <text x={w/2} y={h*0.92} fill="#E8A87C" fontSize={size==="sm"?2.8:4} fontFamily="monospace" textAnchor="middle" opacity="0.6">PRINCETON · 2022</text>
      </svg>
    );
  }
  if (book.cover === "esl") {
    return (
      <svg viewBox={dims} width={w} height={h} className="book-cover" aria-label={book.title}>
        <rect x="0" y="0" width={w} height={h} fill="#1a1530"/>
        <rect x="0" y="0" width="3" height={h} fill="#0c0820"/>
        {/* trees / dendrogram */}
        <g stroke="#9B8FCC" strokeWidth={size==="sm"?0.5:0.8} fill="none" opacity="0.85">
          <path d={`M${w*0.20} ${h*0.55} V ${h*0.30} H ${w*0.80} V ${h*0.55}`}/>
          <path d={`M${w*0.30} ${h*0.55} V ${h*0.40} H ${w*0.50} V ${h*0.55}`}/>
          <path d={`M${w*0.60} ${h*0.55} V ${h*0.40} H ${w*0.70} V ${h*0.55}`}/>
          {[0.20,0.30,0.50,0.60,0.70,0.80].map((x,i)=>(<circle key={i} cx={w*x} cy={h*0.56} r={size==="sm"?1:1.4} fill="#9B8FCC"/>))}
        </g>
        <text x={w/2} y={h*0.78} fill="#E8ECF0" fontSize={size==="sm"?6:9} fontFamily="serif" fontWeight="500" textAnchor="middle">ESL</text>
        <text x={w/2} y={h*0.88} fill="#9B8FCC" fontSize={size==="sm"?3.5:5} fontFamily="monospace" textAnchor="middle" opacity="0.7">HASTIE et al.</text>
      </svg>
    );
  }
  if (book.cover === "wooldridge") {
    return (
      <svg viewBox={dims} width={w} height={h} className="book-cover" aria-label={book.title}>
        <rect x="0" y="0" width={w} height={h} fill="#0e2438"/>
        <rect x="0" y="0" width="3" height={h} fill="#061626"/>
        {/* panel-data grid */}
        <g stroke="#4F9CF9" strokeWidth="0.4" opacity="0.5">
          {[0,1,2,3,4].map(i => <line key={"h"+i} x1={w*0.15} y1={h*(0.18+i*0.08)} x2={w*0.85} y2={h*(0.18+i*0.08)} />)}
          {[0,1,2,3,4,5,6].map(i => <line key={"v"+i} x1={w*(0.15+i*0.11)} y1={h*0.18} x2={w*(0.15+i*0.11)} y2={h*0.5} />)}
        </g>
        <g fill="#4F9CF9">
          {[[0.20,0.22],[0.31,0.30],[0.42,0.26],[0.53,0.34],[0.64,0.38],[0.75,0.42]].map((p,i)=>(<circle key={i} cx={w*p[0]} cy={h*p[1]} r={size==="sm"?0.9:1.4}/>))}
        </g>
        <text x={w/2} y={h*0.70} fill="#E8ECF0" fontSize={size==="sm"?5:7} fontFamily="serif" textAnchor="middle" letterSpacing="0.1em">ECONOMETRIC</text>
        <text x={w/2} y={h*0.78} fill="#E8ECF0" fontSize={size==="sm"?5:7} fontFamily="serif" textAnchor="middle" letterSpacing="0.1em">ANALYSIS</text>
        <text x={w/2} y={h*0.91} fill="#4F9CF9" fontSize={size==="sm"?3.5:5} fontFamily="monospace" textAnchor="middle" opacity="0.8">WOOLDRIDGE</text>
      </svg>
    );
  }
  return null;
}

// ─── Book Card (used inside modal) ───────────────────────────────────────────
function BookCard({ book, onToggle, compact }) {
  return (
    <article className={"book-card" + (book.selected ? " is-selected" : "") + (book.indexed === false ? " is-pending" : "") + (compact ? " is-compact" : "")}>
      <div className="book-card__cover">
        <BookCover book={book} size={compact ? "sm" : "lg"} />
        <span className="book-card__pin" style={{ background: book.color, boxShadow: `0 0 8px ${book.color}` }} />
      </div>
      <div className="book-card__body">
        <div className="book-card__short">{book.short}</div>
        <h3 className="book-card__title">{book.title}</h3>
        {!compact && <div className="book-card__sub">{book.subtitle}</div>}
        <div className="book-card__authors">{book.authors}</div>
        <div className="book-card__edition">{book.edition}</div>
        {!compact && (
          <div className="book-card__stats">
            <div className="book-stat"><span>Chunks</span><b>{book.chunks.toLocaleString()}</b></div>
            <div className="book-stat"><span>Figures</span><b>{book.figures}</b></div>
            <div className="book-stat"><span>Chapters</span><b>{book.chapters}</b></div>
          </div>
        )}
        {!compact && <p className="book-card__desc">{book.description}</p>}
        <div className="book-card__foot">
          <span className="book-card__coll"><code>{book.collection}</code></span>
          {book.indexed === false ? (
            <button className="book-card__btn book-card__btn--idx" type="button">+ Index</button>
          ) : (
            <button
              className={"book-card__toggle" + (book.selected ? " is-on" : "")}
              onClick={() => onToggle(book.id)}
              type="button"
              aria-pressed={book.selected}
            >
              <span className="book-card__toggle-knob" />
              <span className="book-card__toggle-lbl">{book.selected ? "Included" : "Excluded"}</span>
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

// ─── Book Modal ──────────────────────────────────────────────────────────────
function BookModal({ open, onClose, books, onToggle }) {
  const indexed = books.filter(b => b.indexed !== false);
  const pending = books.filter(b => b.indexed === false);
  const selected = books.filter(b => b.selected);
  const kpis = {
    chunks: selected.reduce((a, b) => a + b.chunks, 0),
    figures: selected.reduce((a, b) => a + b.figures, 0),
    chapters: selected.reduce((a, b) => a + b.chapters, 0),
  };
  return (
    <FocusModal open={open} onClose={onClose} size="lg" labelledBy="bm-title">
      <header className="fm__hd fm__hd--kpi">
        <div className="bm-kpis">
          <div className="bm-kpi">
            <div className="bm-kpi__val">{selected.length}<span className="bm-kpi__sub">/{indexed.length}</span></div>
            <div className="bm-kpi__lbl">Selected</div>
          </div>
          <div className="bm-kpi bm-kpi--accent">
            <div className="bm-kpi__val">{kpis.chunks.toLocaleString()}</div>
            <div className="bm-kpi__lbl">Chunks</div>
          </div>
          <div className="bm-kpi">
            <div className="bm-kpi__val">{kpis.figures}</div>
            <div className="bm-kpi__lbl">Figures</div>
          </div>
          <div className="bm-kpi">
            <div className="bm-kpi__val">{kpis.chapters}</div>
            <div className="bm-kpi__lbl">Chapters</div>
          </div>
          <div className="bm-kpi">
            <div className="bm-kpi__val">1024<span className="bm-kpi__sub">d</span></div>
            <div className="bm-kpi__lbl">Vectors</div>
          </div>
        </div>
        <button className="fm__close" onClick={onClose} aria-label="Close">
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><path d="m4 4 8 8M12 4l-8 8"/></svg>
        </button>
      </header>

      <div className="bm-chip-row">
        <div className="bm-chip-row__label">COLLECTIONS</div>
        <div className="bm-chip-row__chips">
          {books.map(b => (
            <button
              key={b.id}
              className={"bm-chip" + (b.selected ? " is-on" : "") + (b.indexed === false ? " is-pending" : "")}
              onClick={() => b.indexed !== false && onToggle(b.id)}
              type="button"
              aria-pressed={b.selected}
              style={b.selected ? { "--chip-tint": b.color } : undefined}
            >
              <span className="bm-chip__dot" style={{ background: b.color }} />
              <span className="bm-chip__name">{b.short}</span>
              <span className="bm-chip__count">{b.chunks.toLocaleString()}</span>
              {b.indexed === false && <span className="bm-chip__pending">not indexed</span>}
            </button>
          ))}
        </div>
        <div className="bm-chip-row__hint">
          {selected.length} active
        </div>
      </div>

      <div className="fm__body">
        {selected.length > 0 ? (
          <div className="book-grid">
            {selected.map(b => <BookCard key={b.id} book={b} onToggle={onToggle} />)}
          </div>
        ) : (
          <div className="bm-empty">
            <div className="bm-empty__glyph">∅</div>
            <div className="bm-empty__title">No collections selected</div>
            <p className="bm-empty__text">Toggle a chip above to include it in retrieval. At least one collection is required for queries to return sources.</p>
          </div>
        )}

        {pending.length > 0 && (
          <div className="bm-pending">
            <div className="bm-pending__hd">
              <span>NOT INDEXED</span>
              <span className="bm-pending__count">{pending.length} available to add</span>
            </div>
            <div className="bm-pending__list">
              {pending.map(b => <BookCard key={b.id} book={b} onToggle={onToggle} compact />)}
            </div>
          </div>
        )}
      </div>

      <footer className="fm__ft">
        <span className="fm__ft-hint">⌘+B to open · Esc to close</span>
        <button className="btn btn--primary" onClick={onClose} type="button">Apply filter</button>
      </footer>
    </FocusModal>
  );
}

// ─── Source Modal — full chunk + highlights ──────────────────────────────────
function highlightSpans(text, highlights) {
  if (!highlights || !highlights.length) return [text];
  // Find each highlight, build interleaved array
  const ranges = [];
  highlights.forEach(h => {
    const idx = text.indexOf(h);
    if (idx >= 0) ranges.push([idx, idx + h.length]);
  });
  ranges.sort((a, b) => a[0] - b[0]);
  // Merge overlapping
  const merged = [];
  for (const r of ranges) {
    if (merged.length && r[0] <= merged[merged.length - 1][1]) {
      merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], r[1]);
    } else merged.push([...r]);
  }
  const out = [];
  let cur = 0;
  for (const [a, b] of merged) {
    if (a > cur) out.push({ text: text.slice(cur, a) });
    out.push({ text: text.slice(a, b), hl: true });
    cur = b;
  }
  if (cur < text.length) out.push({ text: text.slice(cur) });
  return out;
}

function SourceModal({ open, onClose, source }) {
  if (!source) return null;
  const tone = source.score >= 0.8 ? "hi" : source.score >= 0.6 ? "mid" : "low";
  const parts = highlightSpans(source.chunk || "", source.highlights);
  const book = (window.STATRAG_BOOKS || []).find(b => b.id === source.book);
  return (
    <FocusModal open={open} onClose={onClose} size="md" labelledBy="src-title">
      <header className="fm__hd fm__hd--source">
        <div className="src-modal__top">
          <span className={"book-tag book-tag--" + source.book.toLowerCase()}>
            <span className={"dot dot--" + source.book.toLowerCase()} />
            {source.book === "HANSEN" ? "Hansen" : source.book}
          </span>
          <span className="src-modal__rank">RANK #{source.rank}</span>
          <span className={"score-badge score-badge--" + tone}>{source.score.toFixed(2)}</span>
          <span className="src-modal__cid">
            <code>{source.chunkId}</code>
          </span>
        </div>
        <h2 className="fm__title" id="src-title">{source.title}</h2>
        <div className="src-modal__path">
          <span>{book ? book.short : source.book}</span>
          <span className="src-modal__sep">/</span>
          <span>{source.chapter}</span>
          <span className="src-modal__sep">/</span>
          <span>{source.section}</span>
          <span className="src-modal__sep">·</span>
          <span>p.{source.page}</span>
        </div>
        <button className="fm__close" onClick={onClose} aria-label="Close">
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><path d="m4 4 8 8M12 4l-8 8"/></svg>
        </button>
      </header>

      <div className="fm__body">
        <div className="src-modal__legend">
          <span className="src-modal__legend-dot" /> Highlighted spans were used as the matching basis for retrieval.
        </div>
        <div className="src-modal__chunk">
          {parts.map((p, i) =>
            p.hl
              ? <mark key={i} className="src-hl">{p.text}</mark>
              : <React.Fragment key={i}>{p.text}</React.Fragment>
          )}
        </div>

        <div className="src-modal__meta">
          <div className="src-modal__meta-row"><span>Embedding</span><span>{source.embedding}</span></div>
          <div className="src-modal__meta-row"><span>Score</span><span className={"score-text score-text--" + tone}>{source.score.toFixed(4)}</span></div>
          <div className="src-modal__meta-row"><span>Chunk ID</span><span><code>{source.chunkId}</code></span></div>
          <div className="src-modal__meta-row"><span>Highlighted spans</span><span>{source.highlights ? source.highlights.length : 0}</span></div>
        </div>
      </div>

      <footer className="fm__ft">
        <button className="btn" type="button" onClick={onClose}>Close</button>
        <button className="btn btn--ghost" type="button">Open in reader →</button>
      </footer>
    </FocusModal>
  );
}

Object.assign(window, { FocusModal, BookModal, SourceModal, BookCover });
