# 03 — Interactions, States & Flows

User-facing behavior: clicks, hovers, animations, keyboard shortcuts, responsive collapse, loading/error/empty states.

---

## Conversation flow

```
[empty]
   │
   ├─ user types in input bar, hits Enter / clicks send
   │
   ▼
[sending]
   │ POST /chat (SSE) — user message rendered immediately,
   │ assistant slot opens with mode badge + "..." dots
   ▼
[streaming]
   │ word-by-word fade-in of assistant body text
   │ source chips & figure cards fade in after first token
   ▼
[complete]
   │ blinking cursor at end disappears
   │ context panel populates with sources/figures
   │ retrieval metadata accordion (collapsed by default) fills
   ▼
[idle] — ready for next turn
```

---

## State machines

### Per-message lifecycle

```ts
type MessageStatus = 
  | { kind: 'pending' }
  | { kind: 'streaming', tokens: string[] }
  | { kind: 'complete' }
  | { kind: 'error', error: string }
```

UI surface:
- `pending`: three pulsing dots in the mode badge area (`--text-tertiary`).
- `streaming`: blinking cursor `|` after the last token.
- `complete`: cursor removed, source chips & figures fade in (300ms).
- `error`: red strip below the badge with retry button.

### Modal lifecycle

`{open: false} → setOpen(true) → animation in (180ms) → user interacts → close trigger → animation out (revert) → setOpen(false)`.

Close triggers (all should work):
- Click backdrop (`.fm` outside `.fm__panel`)
- Press Esc
- Click `.fm__close`
- Click any explicit "close" button in the footer

While open: `document.body.style.overflow = 'hidden'` to lock background scroll. Restore on close.

### Temp chat lifecycle

```
hover assistant msg → .msg__fork becomes opacity 1 → click →
setTempChatOpen(true), setTempSeed(msgIdx) → main becomes 2-col grid →
TempChat mounts with empty state →
user types → sends → message appended to local TempChat state →
fake "temp chats don't query the corpus" assistant reply →
close button → setTempChatOpen(false) → temp pane unmounts → main reverts to 1-col
```

**Important:** when `tempChatOpen === true`, the hover-fork buttons on all assistant messages should be **hidden**. The prototype passes `forkDisabled={tempChatOpen}` to `<MessageThread>`. Maintain this — only one temp chat at a time.

---

## Keyboard shortcuts

| Key             | Action                                            |
|-----------------|---------------------------------------------------|
| `Enter`         | Send message (when textarea focused)              |
| `Shift+Enter`   | Newline in textarea                               |
| `Esc`           | Close any open modal / popover                    |
| `⌘B` / `Ctrl+B` | Open / close BookModal                            |
| `⌘K` / `Ctrl+K` | Open Mode picker (planned — not wired yet)        |
| `Tab`           | Move focus through interactive elements           |

Implement `⌘B` globally (window listener) so it works from any focus state. The prototype does this in `app.jsx`.

---

## Hover states (all dark-mode values)

| Element                  | Default                              | Hover                                                          |
|--------------------------|--------------------------------------|----------------------------------------------------------------|
| `.conv-item`             | text-secondary                       | bg-tertiary, text-primary, mode icon reveals at right          |
| `.source-card`           | border-subtle                        | accent border, `var(--glow-soft)`, `translateY(-1px)`          |
| `.figure-card`           | border-subtle                        | accent border, `var(--glow-soft)`                              |
| `.src-chip`              | border-subtle, text-secondary        | accent border, text-primary, `0 0 8px rgba(63,169,255,0.3)`    |
| `.books-btn`             | border-subtle                        | accent border, `var(--glow-soft)`                              |
| `.book-card` (in modal)  | border-subtle                        | border-default                                                  |
| `.bm-chip` (not on)      | border-subtle, text-secondary        | border-default, text-primary                                    |
| `.mode-picker__item`     | text-secondary                       | bg-tertiary, text-primary                                       |
| `.mp-item`               | —                                    | rgba(63,169,255,0.06) background                                |
| `.tool-btn`              | text-secondary                       | bg-tertiary, text-primary (mode/model variants: bg only)        |
| `.msg__fork`             | opacity 0, translateX(-4px)          | opacity 1, translateX(0) — only via `.msg--assistant:hover`     |
| `.icon-btn--theme` svg   | —                                    | rotate(20deg)                                                   |
| `.input-bar__send.is-active` | accent bg, accent glow            | brightness 1.08 + scale 1.02                                    |

---

## Focus rings

Use the accent color, with a 3px ring at 16% alpha — never use the browser default outline.

```css
:focus-visible {
  outline: 2px solid var(--accent-primary);
  outline-offset: 2px;
}
.input-bar__field:focus-within {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 3px rgba(63, 169, 255, 0.16), var(--glow-accent);
}
```

Tab order:
1. Skip-link (a11y)
2. Topbar: menu → logo (skip) → Books button → theme toggle → settings → status (skip)
3. Sidebar: new conv → each group's items in order → collapse
4. Main: each message's interactive children (chips, fork button) → input textarea → send → toolbar buttons L→R
5. Context: each source card → each figure card → accordion toggle → meta rows

---

## Responsive breakpoints

The design has three layouts. Use container queries on `.app__body` if your framework supports them; otherwise window media queries are fine.

```
>1280px      Three-column. Sidebar + main + context panel all visible.
768–1280px   Two-column. Sidebar collapses to icon rail. Context panel disappears
             entirely (no rail) — the design intentionally drops it; surfacing
             sources requires opening the SourceModal via chip click instead.
<768px       Single column. Sidebar becomes a bottom sheet or off-canvas overlay.
             Topbar's breadcrumb is hidden. Books-button chip preview hidden,
             only count remains.
```

Specific rules:

```css
@media (max-width: 1280px) {
  .topbar__left      { min-width: auto; }
  .ctx-panel         { display: none; }
  .ctx-rail          { display: none; }
  .topbar__center    { display: none; }
}
@media (max-width: 1120px) {
  /* Temp chat split → stacks vertically */
  .main--split       { grid-template-columns: minmax(0, 1fr); grid-template-rows: 1fr auto; }
  .main__pane--temp  { max-height: 50vh; border-left: 0; border-top: 1px dashed var(--border-default); }
}
@media (max-width: 1100px) {
  .books-btn__chips    { display: none; }
  .books-btn__divider  { display: none; }
}
@media (max-width: 940px) {
  .input-bar__hint   { display: none; }
}
@media (max-width: 900px) {
  .bm-chip-row       { flex-direction: column; align-items: stretch; gap: 8px; }
}
@media (max-width: 880px) {
  .sidebar           { display: none; }       /* or convert to off-canvas */
  .thread, .input-bar { padding-left: 16px; padding-right: 16px; }
}
```

---

## Streaming UI (production)

The prototype is canned. Real streaming:

1. User clicks send → optimistic-append a user message to the thread → clear textarea.
2. Append an assistant message with `status: 'pending'`. Render only the mode badge + three pulsing dots.
3. Open an SSE connection to `/chat`. Parse events:
   - `{type: 'meta', mode, books, sourceCount, latencyMs}` → fill the badge.
   - `{type: 'token', text}` → append to a running string, render via the inline tokenizer (block-aware: `$...$` math, `**...**` bold). Maintain an open paragraph until a `\n\n` arrives, then close it and start a new `<p>`.
   - `{type: 'math_block', tex}` → render KaTeX in displayMode.
   - `{type: 'figure', ref, book, chapter, caption, chart}` → render an inline figure card.
   - `{type: 'source_chip', book, section}` → buffer; emit chip row when stream completes.
   - `{type: 'sources_full', sources: Source[]}` → populate context panel + the chip row.
   - `{type: 'done'}` → mark status `complete`, remove cursor, fade in chips + figure cards (300ms).
   - `{type: 'error', message}` → status `error`, show retry.

Hint to keep the UI snappy: render the mode badge as soon as the first `meta` event arrives (typically within 200–400ms of click). The "0.8s" latency display in the badge should be the time-to-first-meta, not the total time.

---

## Source highlighting accuracy

Highlights inside `<SourceModal>` should come from the **backend**, not be matched on the client. The retrieval step typically already knows which sentences/spans contributed to the embedding similarity. Send `{chunk: string, highlights: {start: number, end: number}[]}` and render character-range slices instead of substring matches.

The prototype's `highlightSpans` (in `modals.jsx`) does substring matching as a placeholder. Replace.

---

## Empty / loading / error states

### Empty thread (new conversation)

Per the spec:

```
          ∑ statrag

   What do you want to understand?

   [📖 Explain a concept]   [🔍 Find a section]
   [🎬 Plan a video]        [📝 Generate a quiz]

   Tip: Press Cmd+K to switch modes
```

Center-aligned, `--text-2xl` for the glyph. Suggestion chips are pressable and pre-fill the input. Not rendered in the prototype (it's mid-conversation) — see spec.

### Empty BookModal (no books selected)

`.bm-empty` shown when `selected.length === 0`:
- `∅` glyph, serif 64px, 0.4 opacity
- "No collections selected" title (serif lg)
- "Toggle a chip above to include it in retrieval. At least one collection is required for queries to return sources." (sans sm)

### Loading: retrieval in progress

Mode badge area: three animated dots in `--text-tertiary`. Send button stays in inactive (non-active) state until streaming completes — disable resends.

### Loading: figure thumbnail

Replace the thumbnail with a skeleton at the same dimensions:
```css
.figure-skeleton {
  background: linear-gradient(90deg, var(--bg-tertiary), var(--bg-elevated), var(--bg-tertiary));
  background-size: 200% 100%;
  animation: shimmer 1.5s linear infinite;
}
@keyframes shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
```

### Error: backend failure

Replace the assistant body with an error card:

```
[!] Couldn't reach Qdrant.    [Retry]
    Embedding service returned 503.
```

- Border-color: `--accent-danger`
- Background: rgba(255, 107, 126, 0.05) (subtle red tint)
- Icon + mono code (e.g. "503 EMBEDDING_TIMEOUT")
- Retry button on right (`.btn--primary` styled, danger-colored)

### Offline (Qdrant disconnected)

`.status-dot` loses `.is-online` class — goes grey + the pulse stops. The Books button could optionally show a "(offline)" hint. Sending should still queue but show an inline warning.

---

## Animations to keep

These are essential to the feel of the app — don't drop them in production:

1. **Status dot pulse** — communicates "the backend is alive."
2. **Streaming dots** in the mode badge — communicates "thinking."
3. **Word-by-word token fade-in** — gives the answer rhythm.
4. **Source chip / figure card fade-in after stream completes** — makes citations feel "discovered" rather than dumped.
5. **Hover-fork "+" reveal** — keeps the UI clean by default but discoverable.
6. **Modal scale+fade entry** — gives focus modals weight.
7. **Theme toggle icon hover rotation** — subtle delight.

These are nice-to-have and can be cut if budget is tight:

1. **Body backdrop radial gradient** — pure ambient, no functional purpose.
2. **Film-grain `body::after`** in dark mode.
3. **Glass-edge inner highlights** — adds polish but readability is unaffected.
4. **Translate-Y on source-card hover** — could be color-only.

---

## Accessibility checklist

Per the design spec:

- [ ] All interactive elements reachable by keyboard.
- [ ] `:focus-visible` rings using `--accent-primary`, never browser defaults.
- [ ] Mode pills (or in this design, the active mode badge) announce mode changes via `aria-live="polite"` region.
- [ ] KaTeX blocks include `aria-label` with a human-readable equation description (the prototype skips this — fix in production).
- [ ] Color is never the only signal. Stance classification (used in Annotate mode) uses **icon + text**, not just color.
- [ ] Minimum contrast ratio **4.5:1** for body text. Re-check against the glass surfaces — they're translucent so contrast depends on what's behind them. Test against the worst case (the bright corner of the radial backdrop).
- [ ] `prefers-reduced-motion`: all transitions/animations collapse to ~0ms. (Already implemented in `styles.css`.)
- [ ] Modal traps focus (Tab loops within the modal until closed). The prototype doesn't fully implement this — add a focus trap in production.
- [ ] Modal restores focus to the trigger element on close (e.g. the Books button if BookModal was opened from it).
- [ ] Source chips and source cards both have `aria-label` describing what they link to (e.g. `aria-label="ISLP chapter 6 section 6.2.1: Ridge Regression — open chunk"`).

---

Continue to → `04_data_model.md`
