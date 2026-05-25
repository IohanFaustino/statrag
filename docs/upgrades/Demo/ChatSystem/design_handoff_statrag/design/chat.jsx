// MessageThread (user bubbles + assistant doc rendering w/ KaTeX) + InputBar
const { useState: _u, useRef: _r, useEffect: _e, useLayoutEffect: _le } = React;

// Render inline tokens: **bold** and $math$
function renderInline(text) {
  // Split on $...$ first, then process **...** in non-math parts.
  const parts = [];
  let i = 0, key = 0;
  while (i < text.length) {
    if (text[i] === "$") {
      const end = text.indexOf("$", i + 1);
      if (end === -1) { parts.push(text.slice(i)); break; }
      parts.push({ math: text.slice(i + 1, end) });
      i = end + 1;
    } else {
      const next = text.indexOf("$", i);
      const chunk = next === -1 ? text.slice(i) : text.slice(i, next);
      parts.push(chunk);
      i = next === -1 ? text.length : next;
    }
  }
  // Now expand bold within string parts
  return parts.flatMap((p, idx) => {
    if (typeof p !== "string") return [<InlineMath key={"m" + idx} tex={p.math} />];
    const out = [];
    const re = /\*\*([^*]+)\*\*/g;
    let last = 0, m;
    while ((m = re.exec(p)) !== null) {
      if (m.index > last) out.push(p.slice(last, m.index));
      out.push(<strong key={"b" + idx + "-" + m.index}>{m[1]}</strong>);
      last = m.index + m[0].length;
    }
    if (last < p.length) out.push(p.slice(last));
    return out.map((x, j) => typeof x === "string" ? <React.Fragment key={idx + "-" + j}>{x}</React.Fragment> : x);
  });
}

function useKatexRender(tex, displayMode) {
  const ref = _r(null);
  _e(() => {
    let cancelled = false;
    const tryRender = () => {
      if (cancelled || !ref.current) return;
      if (window.katex) {
        try {
          window.katex.render(tex, ref.current, { throwOnError: false, displayMode });
        } catch (e) { ref.current.textContent = tex; }
      } else {
        setTimeout(tryRender, 60);
      }
    };
    tryRender();
    return () => { cancelled = true; };
  }, [tex, displayMode]);
  return ref;
}
function InlineMath({ tex }) {
  const ref = useKatexRender(tex, false);
  return <span className="math-inline" ref={ref}>{tex}</span>;
}
function BlockMath({ tex }) {
  const ref = useKatexRender(tex, true);
  return <div className="math-block"><div ref={ref}>{tex}</div></div>;
}

function SourceChip({ chip, onOpen }) {
  return (
    <button className="src-chip" type="button" onClick={() => onOpen && onOpen(chip)}>
      <span className={"dot dot--" + chip.book.toLowerCase()} />
      <span className="src-chip__book">{chip.book === "HANSEN" ? "Hansen" : chip.book}</span>
      <span className="src-chip__sec">{chip.section}</span>
    </button>
  );
}

function InlineFigure({ block }) {
  return (
    <figure className="inline-fig">
      <div className="inline-fig__frame">
        <MicroChart kind={block.chart} />
      </div>
      <figcaption className="inline-fig__cap">
        <span className="inline-fig__tag">
          <span className="dot dot--figure" />
          {block.book} · {block.chapter} · {block.ref}
        </span>
        <span className="inline-fig__text">{block.caption}</span>
      </figcaption>
    </figure>
  );
}

function AssistantMessage({ msg, density, bookFilter, onSourceClick, onFork, forkDisabled, idx }) {
  const modeMeta = window.STATRAG_MODES.find(m => m.id === msg.mode);
  const IconFn = modeMeta && Ic[modeMeta.icon];
  return (
    <article className="msg msg--assistant">
      <div className="msg__badge">
        <span className="msg__badge-icon">{IconFn && <IconFn />}</span>
        <span className="msg__badge-mode">{(modeMeta?.label || msg.mode).toUpperCase()} MODE</span>
        <span className="msg__badge-sep">·</span>
        <span className="msg__badge-books">{msg.books.map(b => b === "HANSEN" ? "Hansen" : b).join(" + ")}</span>
        <span className="msg__badge-sep">·</span>
        <span className="msg__badge-count">{msg.sourceCount} sources</span>
        <span className="msg__badge-sep">·</span>
        <span className="msg__badge-lat">{(msg.latencyMs / 1000).toFixed(1)}s</span>
      </div>
      <div className="msg__body">
        {msg.blocks.map((b, i) => {
          if (b.type === "p") return <p key={i} className="msg__p">{renderInline(b.text)}</p>;
          if (b.type === "math") return <BlockMath key={i} tex={b.tex} />;
          if (b.type === "figure") return <InlineFigure key={i} block={b} />;
          if (b.type === "sources") return (
            <div key={i} className="msg__src-row">
              {b.chips.map((c, j) => <SourceChip key={j} chip={c} onOpen={onSourceClick} />)}
            </div>
          );
          return null;
        })}
      </div>
      {!forkDisabled && (
        <button
          className="msg__fork"
          type="button"
          onClick={() => onFork && onFork(idx)}
          title="Open in temporary chat"
          aria-label="Open in temporary chat"
        >
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M8 3.5v9M3.5 8h9"/></svg>
        </button>
      )}
    </article>
  );
}

function UserMessage({ msg, bubble }) {
  if (bubble) {
    return (
      <div className="msg msg--user-bubble">
        <div className="user-bubble">
          <p>{msg.text}</p>
        </div>
        <div className="user-meta">[you] · {msg.time}</div>
      </div>
    );
  }
  return (
    <div className="msg msg--user-doc">
      <div className="user-doc">
        <div className="user-doc__rail" />
        <div className="user-doc__body">
          <div className="user-doc__meta">YOU · {msg.time}</div>
          <p>{msg.text}</p>
        </div>
      </div>
    </div>
  );
}

function MessageThread({ thread, bubble, onSourceClick, onFork, forkDisabled }) {
  return (
    <div className="thread">
      <div className="thread__inner">
        <div className="thread__day">
          <span className="thread__day-line" />
          <span className="thread__day-label">Today · May 16, 14:31</span>
          <span className="thread__day-line" />
        </div>
        {thread.map((m, i) => (
          m.role === "user"
            ? <UserMessage key={i} msg={m} bubble={bubble} />
            : <AssistantMessage key={i} msg={m} idx={i} onSourceClick={onSourceClick} onFork={onFork} forkDisabled={forkDisabled} />
        ))}
        <div className="thread__streaming">
          <span className="thread__streaming-dot" />
          <span className="thread__streaming-dot" />
          <span className="thread__streaming-dot" />
          <span className="thread__streaming-hint">Continue the conversation below</span>
        </div>
      </div>
    </div>
  );
}

// ─── Model Picker ────────────────────────────────────────────────────────────
function ModelPicker({ activeModel, providers, onChange }) {
  const [open, setOpen] = _u(false);
  let curProvider = null, curModel = null;
  for (const p of providers) {
    const m = p.models.find(mm => mm.id === activeModel);
    if (m) { curProvider = p; curModel = m; break; }
  }
  return (
    <div className="model-picker">
      <button className="tool-btn tool-btn--model" onClick={() => setOpen(o => !o)} type="button">
        <span className="tool-btn__lbl">Model:</span>
        <span className="tool-btn__val">
          {curProvider && <span className="model-dot" style={{ background: curProvider.color }} />}
          {curModel?.name || "Pick a model"}
        </span>
        <Ic.caret />
      </button>
      {open && (
        <>
          <div className="popover-scrim" onClick={() => setOpen(false)} />
          <div className="model-picker__panel">
            <div className="model-picker__hd">
              <span>MODEL</span>
              <span className="model-picker__hd-hint">grouped by provider</span>
            </div>
            {providers.map(p => (
              <div key={p.id} className="mp-group">
                <div className="mp-group__hd">
                  <span className="mp-group__dot" style={{ background: p.color, boxShadow: `0 0 8px ${p.color}` }} />
                  <span className="mp-group__name">{p.name}</span>
                  <span className="mp-group__count">{p.models.length} model{p.models.length === 1 ? "" : "s"}</span>
                </div>
                <div className="mp-group__list">
                  {p.models.map(m => (
                    <button
                      key={m.id}
                      className={"mp-item" + (m.id === activeModel ? " is-active" : "")}
                      onClick={() => { onChange(m.id); setOpen(false); }}
                      type="button"
                    >
                      <div className="mp-item__l">
                        <div className="mp-item__name">{m.name}</div>
                        <div className="mp-item__tag">{m.tagline}</div>
                      </div>
                      <div className="mp-item__r">
                        <span className="mp-item__ctx">{m.ctx}</span>
                        <span className="mp-item__cost" title="Cost tier">{m.cost}</span>
                        <span className={"mp-item__speed mp-item__speed--" + m.speed}>{m.speed}</span>
                      </div>
                      {m.id === activeModel && (
                        <span className="mp-item__check">
                          <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m3 8 4 4 6-8"/></svg>
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ─── Input Bar ───────────────────────────────────────────────────────────────
function InputBar({ activeMode, modes, onModeChange, activeModel, providers, onModelChange }) {
  const [value, setValue] = _u("");
  const [modePopOpen, setModePopOpen] = _u(false);
  const ta = _r(null);
  const cur = modes.find(m => m.id === activeMode) || modes[0];
  const CurIcon = Ic[cur.icon];

  _e(() => {
    if (!ta.current) return;
    ta.current.style.height = "auto";
    ta.current.style.height = Math.min(200, Math.max(24, ta.current.scrollHeight)) + "px";
  }, [value]);

  return (
    <div className="input-bar">
      <div className="input-bar__inner">
        <div className="input-bar__field">
          <textarea
            ref={ta}
            className="input-bar__ta"
            placeholder="Ask anything about statistics…"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            rows={1}
          />
          <button
            className={"input-bar__send" + (value.trim() ? " is-active" : "")}
            type="button"
            aria-label="Send"
          >
            <Ic.send />
          </button>
        </div>
        <div className="input-bar__toolbar">
          <button className="tool-btn" type="button">
            <Ic.attach />
            <span>Attach</span>
          </button>
          <button className="tool-btn" type="button">
            <Ic.sigma />
            <span>Math</span>
          </button>
          <div className="tool-divider" />
          <div className="mode-picker">
            <button className="tool-btn tool-btn--mode" onClick={() => setModePopOpen(o => !o)} type="button">
              <span className="tool-btn__lbl">Mode:</span>
              <span className="tool-btn__val">
                {CurIcon && <CurIcon />}
                {cur.label}
              </span>
              <Ic.caret />
            </button>
            {modePopOpen && (
              <>
                <div className="popover-scrim" onClick={() => setModePopOpen(false)} />
                <div className="mode-picker__panel">
                  <div className="mode-picker__hd">Switch mode <kbd>⌘K</kbd></div>
                  <div className="mode-picker__grid">
                    {modes.map(m => {
                      const I = Ic[m.icon];
                      return (
                        <button
                          key={m.id}
                          className={"mode-picker__item" + (m.id === activeMode ? " is-active" : "")}
                          onClick={() => { onModeChange(m.id); setModePopOpen(false); }}
                          type="button"
                        >
                          {I && <I />}
                          <span>{m.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </>
            )}
          </div>
          <ModelPicker activeModel={activeModel} providers={providers} onChange={onModelChange} />
          <div className="input-bar__hint">
            <kbd>⏎</kbd> send · <kbd>⇧⏎</kbd> newline
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Temporary side-by-side chat ─────────────────────────────────────────────
function TempChat({ onClose, seedFromMsg }) {
  const [value, setValue] = _u("");
  const [messages, setMessages] = _u([]);
  const ta = _r(null);

  _e(() => {
    if (!ta.current) return;
    ta.current.style.height = "auto";
    ta.current.style.height = Math.min(160, Math.max(24, ta.current.scrollHeight)) + "px";
  }, [value]);

  const send = () => {
    const v = value.trim();
    if (!v) return;
    setMessages(prev => [
      ...prev,
      { role: "user", text: v, time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) },
      { role: "assistant", text: "Temporary chats don't query the corpus — they're for quick side threads. Wire me to `window.claude.complete` to make me answer.", time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) },
    ]);
    setValue("");
  };

  return (
    <div className="temp-chat">
      <header className="temp-chat__hd">
        <div className="temp-chat__hd-left">
          <span className="temp-chat__badge">
            <svg viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><circle cx="8" cy="8" r="5"/><path d="M8 5v3l2 1"/></svg>
            TEMPORARY
          </span>
          <span className="temp-chat__title">Side thread</span>
          {seedFromMsg != null && (
            <span className="temp-chat__seed">forked from msg #{seedFromMsg + 1}</span>
          )}
        </div>
        <div className="temp-chat__hd-right">
          <span className="temp-chat__hint">won't be saved</span>
          <button className="temp-chat__close" onClick={onClose} type="button" aria-label="Close temporary chat">
            <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="m4 4 8 8M12 4l-8 8"/></svg>
          </button>
        </div>
      </header>

      <div className="temp-chat__body">
        {messages.length === 0 ? (
          <div className="temp-chat__empty">
            <div className="temp-chat__empty-glyph">∿</div>
            <div className="temp-chat__empty-title">A side thread</div>
            <p className="temp-chat__empty-text">
              Ask a quick question without polluting your main conversation. Nothing here is saved, indexed, or carried forward.
            </p>
            <div className="temp-chat__empty-suggest">
              {[
                "Explain this in one paragraph",
                "What's the LASSO analogue?",
                "Give me a concrete example",
              ].map(s => (
                <button key={s} className="temp-chat__sugg" type="button" onClick={() => setValue(s)}>{s}</button>
              ))}
            </div>
          </div>
        ) : (
          <div className="temp-chat__msgs">
            {messages.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="temp-msg temp-msg--user">
                  <div className="temp-msg__bubble">{m.text}</div>
                  <div className="temp-msg__meta">{m.time}</div>
                </div>
              ) : (
                <div key={i} className="temp-msg temp-msg--assistant">
                  <div className="temp-msg__meta">temp · {m.time}</div>
                  <p className="temp-msg__text">{m.text}</p>
                </div>
              )
            )}
          </div>
        )}
      </div>

      <div className="temp-chat__input">
        <div className="temp-chat__field">
          <textarea
            ref={ta}
            placeholder="Ask in this side thread…"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            rows={1}
          />
          <button
            className={"temp-chat__send" + (value.trim() ? " is-active" : "")}
            type="button"
            onClick={send}
            aria-label="Send"
          >
            <Ic.send />
          </button>
        </div>
        <div className="temp-chat__footer">
          <span><kbd>⏎</kbd> send</span>
          <span>·</span>
          <span>not saved to history</span>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { MessageThread, InputBar, AssistantMessage, UserMessage, TempChat });
