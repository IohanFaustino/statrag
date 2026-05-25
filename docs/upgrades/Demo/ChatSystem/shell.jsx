// Topbar, Sidebar, ContextPanel
const { useState, useRef, useEffect } = React;

// ─── Topbar ──────────────────────────────────────────────────────────────────
function Topbar({ activeConvTitle, books, online, onToggleSidebar, onOpenBooks, onOpenSettings, theme, onToggleTheme }) {
  const selected = books.filter(b => b.selected);
  const allSelected = selected.length === books.filter(b => b.indexed !== false).length;
  return (
    <header className="topbar">
      <div className="topbar__left">
        <button className="topbar__menu" onClick={onToggleSidebar} aria-label="Toggle sidebar" type="button">
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><path d="M2.5 4h11M2.5 8h11M2.5 12h11"/></svg>
        </button>
        <div className="logo">
          <span className="logo__mark" aria-hidden="true">∑</span>
          <span className="logo__word">statrag</span>
        </div>
      </div>

      <div className="topbar__center">
        <div className="topbar__breadcrumb">
          <span className="topbar__crumb-dim">Today</span>
          <span className="topbar__crumb-sep">/</span>
          <span className="topbar__crumb-title">{activeConvTitle}</span>
        </div>
      </div>

      <div className="topbar__right">
        <button className="books-btn" onClick={onOpenBooks} type="button">
          <span className="books-btn__icon" aria-hidden="true">
            <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 2.5h4.5a2 2 0 0 1 2 2v9"/>
              <path d="M13 2.5H8.5a2 2 0 0 0-2 2v9"/>
              <path d="M3 11.5h4.5a2 2 0 0 1 2 2"/>
              <path d="M13 11.5H8.5a2 2 0 0 0-2 2"/>
            </svg>
          </span>
          <span className="books-btn__lbl">Books</span>
          <span className="books-btn__divider" />
          <span className="books-btn__chips">
            {allSelected ? (
              <span className="books-btn__all">ALL</span>
            ) : selected.length === 0 ? (
              <span className="books-btn__none">none</span>
            ) : selected.map(b => (
              <span key={b.id} className="books-btn__chip">
                <span className="dot" style={{ background: b.color }} />
                {b.short}
              </span>
            ))}
          </span>
          <span className="books-btn__count">{selected.length}/{books.filter(b => b.indexed !== false).length}</span>
        </button>
        <div className="topbar__divider" />
        <button
          className={"icon-btn icon-btn--theme is-" + (theme || "dark")}
          onClick={onToggleTheme}
          aria-label={"Switch to " + (theme === "dark" ? "light" : "dark") + " mode"}
          title={(theme === "dark" ? "Light" : "Dark") + " mode"}
          type="button"
        >
          {theme === "dark" ? (
            /* Sun (currently dark, click → light) */
            <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="8" cy="8" r="3"/>
              <path d="M8 1.5v1.5M8 13v1.5M1.5 8h1.5M13 8h1.5M3.5 3.5l1 1M11.5 11.5l1 1M12.5 3.5l-1 1M4.5 11.5l-1 1"/>
            </svg>
          ) : (
            /* Moon (currently light, click → dark) */
            <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M13.5 9.2A5.5 5.5 0 0 1 6.8 2.5a5.5 5.5 0 1 0 6.7 6.7Z"/>
            </svg>
          )}
        </button>
        <button className="icon-btn" onClick={onOpenSettings} aria-label="Settings" type="button"><Ic.gear /></button>
        <div className={"status-dot" + (online ? " is-online" : "")} title={online ? "Qdrant live" : "Offline"} />
      </div>
    </header>
  );
}

// ─── Sidebar ─────────────────────────────────────────────────────────────────
function ConvItem({ conv }) {
  const modeIcon = Ic[(window.STATRAG_MODES.find(m => m.id === conv.mode) || {}).icon];
  return (
    <button className={"conv-item" + (conv.active ? " is-active" : "")} type="button">
      <span className="conv-item__title">{conv.title}</span>
      <span className="conv-item__mode">{modeIcon && React.createElement(modeIcon)}</span>
    </button>
  );
}

function Sidebar({ collapsed, convs, roadmaps }) {
  if (collapsed) {
    return (
      <aside className="sidebar sidebar--collapsed">
        <button className="rail-btn rail-btn--new" type="button" title="New conversation"><Ic.plus /></button>
        <div className="rail-divider" />
        <button className="rail-btn" title="Today"><span className="rail-badge">2</span></button>
        <button className="rail-btn" title="Yesterday"><span className="rail-badge">2</span></button>
        <button className="rail-btn" title="This week"><span className="rail-badge">3</span></button>
        <div style={{ flex: 1 }} />
        <button className="rail-btn" title="Settings"><Ic.gear /></button>
      </aside>
    );
  }
  const groups = [
    { label: "Today", items: convs.today },
    { label: "Yesterday", items: convs.yesterday },
    { label: "This week", items: convs.thisWeek },
    { label: "Earlier", items: convs.earlier },
  ];
  return (
    <aside className="sidebar">
      <button className="new-conv" type="button">
        <Ic.plus />
        <span>New conversation</span>
        <span className="new-conv__spark"><Ic.spark /></span>
      </button>

      <div className="sidebar__scroll">
        {groups.map(g => (
          <div className="sb-group" key={g.label}>
            <div className="sb-group__label">{g.label}</div>
            <div className="sb-group__list">
              {g.items.map(c => <ConvItem key={c.id} conv={c} />)}
            </div>
          </div>
        ))}

        <div className="sb-divider" />

        <div className="sb-group">
          <div className="sb-group__label sb-group__label--ts">Roadmaps</div>
          <div className="sb-group__list">
            {roadmaps.map(r => (
              <button key={r.id} className="roadmap-item" type="button">
                <span className="roadmap-item__title">{r.title}</span>
                <span className="roadmap-item__meta">
                  <span className="roadmap-item__scenes">{r.scenes} scenes</span>
                  <span className="roadmap-item__date">{r.date}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <button className="sb-collapse" type="button" title="Collapse sidebar">
        <Ic.chevL />
      </button>
    </aside>
  );
}

// ─── Right Context Panel ─────────────────────────────────────────────────────
function ScoreBadge({ score }) {
  let tone = "low";
  if (score >= 0.8) tone = "hi";
  else if (score >= 0.6) tone = "mid";
  return <span className={"score-badge score-badge--" + tone}>{score.toFixed(2)}</span>;
}

function SourceCard({ src, onOpen }) {
  return (
    <button className="source-card" type="button" onClick={() => onOpen && onOpen(src)}>
      <div className="source-card__hd">
        <span className={"book-tag book-tag--" + src.book.toLowerCase()}>
          <span className={"dot dot--" + src.book.toLowerCase()} />
          {src.book === "HANSEN" ? "Hansen" : src.book}
        </span>
        <span className="source-card__hd-right">
          <span className="source-card__rank">#{src.rank}</span>
          <ScoreBadge score={src.score} />
        </span>
      </div>
      <div className="source-card__path">{src.chapter} · {src.section}</div>
      <div className="source-card__title">{src.title}</div>
      <div className="source-card__excerpt">"{src.excerpt}"</div>
    </button>
  );
}

function FigureCard({ fig }) {
  return (
    <button className="figure-card" type="button">
      <div className="figure-card__hd">
        <span className="book-tag book-tag--figure"><span className="dot dot--figure" /> Figure</span>
        <span className="figure-card__path">{fig.book} · {fig.chapter} · {fig.ref}</span>
      </div>
      <div className="figure-card__thumb">
        <MicroChart kind={fig.chart} />
      </div>
      <div className="figure-card__caption">"{fig.caption}"</div>
    </button>
  );
}

function ContextPanel({ sources, figures, metadata, collapsed, onToggle, onSourceClick }) {
  const [metaOpen, setMetaOpen] = useState(false);
  if (collapsed) {
    return (
      <button className="ctx-rail" onClick={onToggle} type="button" title="Show sources">
        <Ic.chevL />
        <span className="ctx-rail__label">SOURCES</span>
        <span className="ctx-rail__count">{sources.length}</span>
      </button>
    );
  }
  return (
    <aside className="ctx-panel">
      <button className="ctx-panel__collapse" onClick={onToggle} type="button" title="Hide panel">
        <Ic.chevR />
      </button>

      <div className="ctx-panel__scroll">
        <div className="ctx-section">
          <div className="ctx-section__hd">
            <span className="ctx-section__label">Sources</span>
            <span className="ctx-section__count">({sources.length})</span>
          </div>
          <div className="ctx-section__list">
            {sources.map(s => <SourceCard key={s.rank} src={s} onOpen={onSourceClick} />)}
          </div>
        </div>

        <div className="ctx-section">
          <div className="ctx-section__hd">
            <span className="ctx-section__label">Figures</span>
            <span className="ctx-section__count">({figures.length})</span>
          </div>
          <div className="ctx-section__list">
            {figures.map(f => <FigureCard key={f.ref} fig={f} />)}
          </div>
        </div>

        <div className="ctx-section">
          <button className="ctx-acc" onClick={() => setMetaOpen(o => !o)} type="button">
            <span className={"ctx-acc__caret" + (metaOpen ? " is-open" : "")}><Ic.caret /></span>
            <span className="ctx-section__label">Retrieval</span>
          </button>
          {metaOpen && (
            <div className="ctx-meta">
              <div className="ctx-meta__row"><span>Query (rewritten)</span><span className="ctx-meta__val">"{metadata.rewrittenQuery}"</span></div>
              <div className="ctx-meta__row"><span>Embedding</span><span className="ctx-meta__val">{metadata.embedding}</span></div>
              <div className="ctx-meta__row"><span>Retrieval</span><span className="ctx-meta__val">{metadata.retrievalMs}ms</span></div>
              <div className="ctx-meta__row"><span>Mode</span><span className="ctx-meta__val">{metadata.mode}</span></div>
              <div className="ctx-meta__row"><span>top-K</span><span className="ctx-meta__val">{metadata.topK}</span></div>
              <div className="ctx-meta__row"><span>score ≥</span><span className="ctx-meta__val">{metadata.scoreThreshold}</span></div>
              <div className="ctx-meta__row"><span>Filter</span><span className="ctx-meta__val">{metadata.filter}</span></div>
              <div className="ctx-meta__row"><span>Collections</span><span className="ctx-meta__val">{metadata.collections.join(", ")}</span></div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

Object.assign(window, { Topbar, Sidebar, ContextPanel });
