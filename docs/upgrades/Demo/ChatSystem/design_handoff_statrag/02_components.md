# 02 — Components

Every UI component with anatomy, props, states, and CSS class mapping. Reference `design/shell.jsx`, `design/chat.jsx`, `design/modals.jsx` while reading.

---

## Hierarchy

```
<App>
├── <Topbar>
│   ├── menu toggle button
│   ├── <Logo>
│   ├── <Breadcrumb>
│   └── right cluster
│       ├── <BooksButton> ──── opens BookModal
│       ├── <ThemeToggle>
│       ├── settings icon button
│       └── <StatusDot>
├── <Sidebar>          (or rail when collapsed)
│   ├── New conversation button
│   ├── <ConversationList> grouped by Today/Yesterday/This week/Earlier
│   ├── <RoadmapList>
│   └── collapse handle
├── <Main>             (becomes a 2-col grid when temp chat is open)
│   ├── <MainPane primary>
│   │   ├── <MessageThread>
│   │   │   ├── day rule
│   │   │   ├── <UserMessage> | <AssistantMessage> …
│   │   │   └── streaming dots placeholder
│   │   └── <InputBar>
│   │       ├── textarea + send button
│   │       └── toolbar: Attach · Math · Mode · Model · hint
│   └── <MainPane temp>   ← only when forked
│       └── <TempChat>
│           ├── header (TEMPORARY badge + close)
│           ├── empty state OR messages
│           └── temp input bar
├── <ContextPanel>     (or rail when collapsed)
│   ├── Sources section
│   ├── Figures section
│   └── Retrieval metadata accordion
├── <BookModal>        (focus modal)
└── <SourceModal>      (focus modal)
```

---

## App-level state

Held in `<App>`:

```ts
{
  // tweaks (theme, accent, density, font pair, sidebar/context open, user msg style)
  // — these live in TweaksPanel state in the prototype; in production
  //   make them user preferences (localStorage / server)
  
  sidebarCollapsed: boolean
  contextCollapsed: boolean
  books: Book[]                        // selected state per book
  booksModalOpen: boolean
  openSource: Source | null            // currently focused source (null = closed)
  tempChatOpen: boolean
  tempSeed: number | null              // index of the assistant message that spawned the temp chat
  activeModel: string                  // model id, e.g. "gpt-4o"
  
  // not in prototype but needed in production:
  activeConversationId: string | null
  mode: Mode                           // tutor | compare | quiz | …
  bookFilter: 'ALL' | string[]         // collection ids
  isStreaming: boolean
}
```

Theme/density/accent/fonts are applied as CSS variables on `<html>` via a `useEffect` that watches the tweaks state. See `app.jsx`.

---

## Topbar — `<Topbar>`

**Position:** sticky top, height 48px, glass surface (`--bg-secondary` + backdrop-filter).

### Anatomy

```
┌────────────────────────────────────────────────────────────────────────┐
│ [≡] [∑ statrag]    Today / Ridge vs OLS in Hansen    [Books|ISLP+Hans] [☼] [⚙] [●] │
└────────────────────────────────────────────────────────────────────────┘
```

| Slot           | Component / class                  | Notes                                    |
|----------------|------------------------------------|------------------------------------------|
| Menu toggle    | `.topbar__menu`                    | Triple-line icon, toggles sidebar.       |
| Logo           | `.logo` → `.logo__mark` `.logo__word` | `∑` glyph in serif, accent-colored, **with text-shadow glow** in dark; `statrag` wordmark in mono. |
| Breadcrumb     | `.topbar__center` → `.topbar__breadcrumb` | `Today / <conversation title>`. Dimmed parent, primary-color title in serif. Hidden at `<1280px`. |
| Books button   | `.books-btn`                       | See **BooksButton** below.               |
| Theme toggle   | `.icon-btn.icon-btn--theme.is-{dark|light}` | Sun icon in dark mode (click → light), moon in light. Glass icon button; rotates 20° on hover. |
| Settings       | `.icon-btn`                        | Gear icon — drawer not designed yet (placeholder).|
| Status dot     | `.status-dot.is-online`            | 8px circle, accent color, **animated pulse ring** (radial 0.8 → 1.8 scale, 2s loop).|

### Props (sketch)

```ts
type TopbarProps = {
  activeConvTitle: string
  books: Book[]                        // for the BooksButton preview chips + count
  online: boolean
  theme: 'dark' | 'light'
  onToggleSidebar(): void
  onOpenBooks(): void
  onOpenSettings(): void
  onToggleTheme(): void                // must also swap accent — see app.jsx
}
```

### BooksButton — `.books-btn`

Compact rectangular button with these inner parts:

```
[📚] Books | [● ISLP] [● Hansen]  2/2
 │     │           │              └─ count badge (mono, bg-elevated, small)
 │     │           └─ live preview chips of currently selected books
 │     └─ "Books" label in mono / text-tertiary
 └─ stack-of-books SVG icon (with drop-shadow glow)
```

When more books are selected than fit (>2 typically): show "ALL" instead of chips if everything is selected, or "none" in danger color if nothing.

Hover: accent border, `var(--glow-soft)` box-shadow.
Click: opens BookModal.

### Theme toggle behavior

The button toggles `data-theme` on `<html>` AND must also swap the accent color in lockstep:

```ts
onToggleTheme = () => {
  const next = theme === 'dark' ? 'light' : 'dark'
  setTheme(next)
  setAccent(next === 'dark' ? '#3FA9FF' : '#001F3F')
}
```

If you skip the accent swap, the user's accent (which CSS-applies via inline style) will override the theme's natural accent and look wrong (neon blue on cream paper).

---

## Sidebar — `<Sidebar>`

**Position:** left, 260px (collapsed: 52px icon rail), glass surface.

### Anatomy

```
┌──────────────────┐
│ [+ New convers.] │   ← dashed border, accent-color hover
├──────────────────┤
│ TODAY            │   ← uppercase mono label
│  Ridge vs OLS    │   ← active: bg-tertiary + 2px accent rail on left
│  Cross-val pit…  │
│ YESTERDAY        │
│  Bootstrap …     │
│  Quiz: Linear …  │
│ THIS WEEK        │
│  …               │
│                  │
│ - - - - - - - -  │   ← divider
│ ROADMAPS         │   ← mono uppercase, letter-spacing 0.12em
│  Bias-Var Trade… │
│  ↳ 11 scenes · 5/12 │
│  From OLS to …   │
│                  │
├──────────────────┤
│ [<]              │   ← collapse handle
└──────────────────┘
```

| Slot                | Class                                | Notes |
|---------------------|--------------------------------------|-------|
| New conversation    | `.new-conv`                          | 36px height, **1px dashed** border-default, becomes solid + accent on hover; `+` icon and tiny spark glyph at end. |
| Group label         | `.sb-group__label` `.sb-group__label--ts` (mono variant for ROADMAPS) | Uppercase, `--text-xs`, letter-spacing 0.08em (sans) or 0.12em (mono). |
| Conv item           | `.conv-item` `.is-active`            | 36px (comfortable) / 30px (compact). Hover shows the mode icon at the right (opacity 0 → 1). Active: bg-tertiary + 2px accent rail at left + serif title weight 500. |
| Roadmap item        | `.roadmap-item`                      | Serif title + mono meta line ("11 scenes · May 12"). |
| Collapse handle     | `.sb-collapse`                       | Left-chevron, full-width 32px row at bottom. |

### Collapsed rail — `.sidebar--collapsed`

When collapsed to 52px:
- New-conv button shrinks to icon-only.
- Each group becomes a single rail row with a number badge ("Today · 2").
- Settings icon at the bottom.

Width transition: 200ms ease-out.

### Conversation data

```ts
type Conversation = {
  id: string
  title: string
  mode: ModeId                  // for the right-side mode icon hover affordance
  active?: boolean              // exactly one across the whole list
}

// grouped:
type ConversationGroups = {
  today: Conversation[]
  yesterday: Conversation[]
  thisWeek: Conversation[]
  earlier: Conversation[]
}
```

Server-side: bucket by relative date. Don't bucket on client unless the conversation count is small (<200).

---

## Context Panel — `<ContextPanel>` (right)

**Position:** right, 320px (collapsed: 36px rail), glass surface, hidden at `<1280px`.

### Sections (top → bottom)

#### 1. Sources

`.ctx-section` → `.ctx-section__hd` ("SOURCES (4)" — mono uppercase, letter-spacing 0.12em) → `.ctx-section__list` containing `<SourceCard>` × N.

**`<SourceCard>` anatomy:**

```
┌────────────────────────────────────┐
│ ● ISLP                  #1   0.94  │   ← book tag (dot + name)  · rank · score badge
│ ch06 · §6.2.1                      │   ← mono path
│ Ridge Regression                   │   ← serif title
│ "the penalty term λΣβⱼ²            │   ← italic excerpt, 2-line clamp
│  shrinks the coefficients…"        │
└────────────────────────────────────┘
```

| Element       | Class                          | Notes |
|---------------|--------------------------------|-------|
| Book tag      | `.book-tag.book-tag--{islp\|hansen}` + `.dot.dot--{islp\|hansen}` | dot color from book brand. |
| Rank          | `.source-card__rank`           | mono, "#1" / "#2" / … |
| Score badge   | `.score-badge.score-badge--{hi\|mid\|low}` | hi ≥ 0.8 (sage green), mid 0.6–0.8 (amber), low <0.6 (red). |
| Section path  | `.source-card__path`           | mono, e.g. "ch06 · §6.2.1". |
| Title         | `.source-card__title`          | serif, weight 500. |
| Excerpt       | `.source-card__excerpt`        | italic, 2-line clamp via `-webkit-line-clamp`. |

Hover: accent border, `var(--glow-soft)`, `translateY(-1px)`.
Click: opens `<SourceModal>` with the full chunk.

#### 2. Figures

Same `.ctx-section` shell. Each `<FigureCard>`:

```
┌────────────────────────────────────┐
│ ● Figure       ISLP · ch06 · fig_6_4│
│ ┌──────────────────────────────┐    │
│ │   [4:3 thumbnail]            │    │   ← bg #000 in dark, navy #001f3f in light
│ └──────────────────────────────┘    │
│ "Bias-variance tradeoff as λ varies"│   ← italic caption
└────────────────────────────────────┘
```

Click: lightbox (not designed yet — placeholder behavior).

#### 3. Retrieval Metadata (collapsible accordion)

`.ctx-acc` button + `.ctx-acc__caret` (rotates 0° → -90°) + `.ctx-meta` body.

Rows: 90px label / 1fr value, mono, very small. Fields shown:

- Query (rewritten)
- Embedding
- Retrieval (ms)
- Mode (e.g. "hybrid (sparse 0.3 + dense 0.7)")
- top-K
- score threshold
- Filter
- Collections

### Collapse / expand

Click `.ctx-panel__collapse` (chevron handle on the panel's left edge) to slide the panel away. The rail (`.ctx-rail`) is a 36px vertical strip showing "SOURCES" rotated 90° + the count in accent color.

---

## Main pane

### `<MessageThread>`

Container: `.thread` (overflow-y auto, max-width 720px centered, padding 24/32/16/32). Cosmic backdrop shows through (transparent background).

Children order:
1. Day rule — `.thread__day` (two horizontal lines + centered mono label like "Today · May 16, 14:31").
2. Messages — `<UserMessage>` or `<AssistantMessage>`.
3. Streaming hint — `.thread__streaming` (three pulsing dots + "Continue the conversation below").

Gap between messages: `var(--thread-gap)` (18px compact / 28px comfortable).

### `<UserMessage>`

Two variants picked by user preference (Tweaks "user msg" toggle):

**Bubble** (`.msg--user-bubble`) — default. Right-aligned, `--bg-elevated` background, `border-radius: 12px 12px 2px 12px`, max-width 480px. Below the bubble: `[you] · 14:32` in mono / tertiary.

**Document** (`.msg--user-doc`) — full-width. 2px accent-color rail on left, serif body text at weight 500, mono "YOU · 14:32" header label in accent.

### `<AssistantMessage>`

Left-aligned, **no background bubble** — renders directly on the page. Gives a "document" feel.

```
[icon] TUTOR MODE · ISLP + HANSEN · 3 sources · 0.8s         ← .msg__badge
                                                              (mono, --text-xs)

Ridge regression extends ordinary least squares by adding…    ← .msg__p
                                                              (sans, --text-base, line-height 1.65)

┌─────────────────────────────────────────┐
│  β̂_ridge = argmin ‖y − Xβ‖² + λ‖β‖²    │  ← .math-block (KaTeX, displayMode=true)
└─────────────────────────────────────────┘    bg --code-surface, border subtle,
                                                tiny "math" label top-right

**Hansen (ch07, §7.4)** frames this explicitly…              ← serif strong inline

[● ISLP ch06 §6.2] [● Hansen ch07 §7.4] [● ISLP ch06 §6.2.1] ← .src-chip row
```

| Element              | Class               | Notes |
|----------------------|---------------------|-------|
| Mode badge           | `.msg__badge`       | Inline mono metadata row (icon · MODE · books · N sources · latency). Latency is sage-green. |
| Body paragraph       | `.msg__p`           | Sans, base size, 1.65 line-height, **text-wrap: pretty**. Supports inline `**bold**` (serif, weight 600) and inline `$math$` (KaTeX inline). |
| Math block           | `.math-block`       | KaTeX display mode. Tiny "MATH" label at top-right corner. |
| Inline figure        | `.inline-fig` → `.inline-fig__frame` `.inline-fig__cap` | 16:9 thumbnail + caption row (mono book/chapter/ref tag in neutral-lilac + italic caption). |
| Source chips         | `.msg__src-row` containing `.src-chip` × N | Mini "book ch07 §7.4" pills. Hover: accent border + soft glow. Click: open SourceModal. |
| Hover-fork "+" button| `.msg__fork`        | Absolute-positioned 28×28 button at top-right (translated outside the message bubble: `right: -36px`). Hidden by default (opacity 0); visible on `.msg--assistant:hover`. Has a "Open in side thread" tooltip pseudo-element. |

#### Rendering rules

- The assistant message body is a **block sequence** — each entry is `{type: 'p' | 'math' | 'figure' | 'sources', ...}`. Render in order. Keep this as the data shape; don't try to merge into a single markdown string.
- Inline tokenization: split `$...$` for math first, then `**...**` for bold within the remaining string fragments. The prototype has a 20-line implementation in `chat.jsx`'s `renderInline`. Replace with a real markdown library (`react-markdown` + `rehype-katex`) in production — but keep the same `{type: ...}` block API.
- KaTeX: wait for `window.katex` to exist before calling `katex.render`. If async-loading, the prototype retries every 60ms.

### `<InputBar>` — `.input-bar`

Sticky-bottom area. Two rows:

**Row 1 — field:** `.input-bar__field` (glass, border subtle, radius 10px, focus glow). Contains a 1fr auto-expanding textarea (min 24px, max 200px) and a 36×36 send button on the right.

The send button has two states:
- Inactive: bg-elevated, text-tertiary, no glow.
- `.is-active` (when textarea has trimmed content): accent background, inverse text, `var(--glow-accent)` shadow. Hover: brightness 1.08 + scale 1.02.

**Row 2 — toolbar:** small mono buttons at 26px height. Order, left → right:

1. `[📎 Attach]` — opens file picker (for annotate/research modes).
2. `[∑ Math]` — toggles a small LaTeX helper overlay (not designed yet).
3. divider
4. `<ModePicker>` — `.tool-btn--mode` opens `.mode-picker__panel`.
5. `<ModelPicker>` — `.tool-btn--model` opens `.model-picker__panel`.
6. spacer / mono hint `⏎ send · ⇧⏎ newline` (`.input-bar__hint`).

Keyboard:
- Enter → send.
- Shift+Enter → newline.
- ⌘K → open Mode picker (handler can live globally).

### `<ModePicker>`

Popover anchored to the Mode button (`bottom: 100% + 8px; left: 0`). Width 320px, padding 10px, glass background.

Header: "Switch mode  ⌘K".
Body: 3-column grid of `.mode-picker__item` × 11 (Tutor, Compare, Figures, Quiz, Navigate, Prereqs, Annotate, Research, Math, Path, Roadmap). Each item is icon-on-top, label-below, 10px padding, 7px radius.

Active item gets accent border + inset accent glow + the icon turns accent-colored.

### `<ModelPicker>`

Popover anchored to the Model button. Width 360px, padding 8px, glass.

Header: `MODEL · grouped by provider`.

Body: provider groups (`.mp-group`), each with:
- `.mp-group__hd` — colored dot (with glow shadow at provider color) + serif name + mono count "4 models".
- `.mp-group__list` — `.mp-item` rows.

Each `.mp-item`:

```
┌─────────────────────────────────────────────┐
│ GPT-4o                       128k  $$$  FAST │
│ Fast multimodal                              │
└─────────────────────────────────────────────┘
```

- `.mp-item__l` → name (sans, weight 500) + tagline (mono).
- `.mp-item__r` → context window pill (`.mp-item__ctx`) + cost (`.mp-item__cost`, sage-green) + speed badge (`.mp-item__speed--fast|med|slow`, color-coded).

Active model: light-accent background + inset accent glow + small ✓ in the top-right corner (`.mp-item__check`).

### `<TempChat>` — `.temp-chat`

Side-by-side temporary chat. Appears when user clicks the `+` button on an assistant message. The main column becomes a 2-column grid (`.main--split`): primary pane + temp pane.

- Background: tinted lilac (`accent-neutral`) — `linear-gradient(180deg, mix(neutral 7%, primary), mix(neutral 4%, primary))` + a 45° diagonal hatch pseudo-element overlay at low opacity. Border-left: 1px dashed `--border-default`.
- Header (`.temp-chat__hd`): 38px, glass-tinted with `accent-neutral`. Shows `[TEMPORARY]` badge (mono uppercase, neutral-color, glowing border), "Side thread" title (serif), and "forked from msg #N" mono hint. Right side: "won't be saved" + close ×.
- Body: empty state (large `∿` glyph, "A side thread" serif title, paragraph, 3 suggestion chips) → switches to message list once user sends.
- Input: small variant of the main InputBar with its own send button (uses neutral-color when active instead of accent).

Responsive: below 1120px the split stacks vertically (max-height 50vh for the temp pane).

---

## Modals

### `<FocusModal>` — generic wrapper

Backdrop: `.fm` fixed full-screen, `rgba(2,6,14,0.72)` + `backdrop-filter: blur(8px) saturate(140%)`. Click backdrop to close.

Panel: `.fm__panel`, glass surface, border `rgba(63,169,255,0.15)`, shadow includes a navy/blue glow:
```
box-shadow:
  0 30px 80px rgba(0, 0, 0, 0.65),
  0 0 0 1px rgba(63, 169, 255, 0.10) inset,
  0 0 80px rgba(63, 169, 255, 0.10);
```

Sizes: `.fm__panel--default` 720px, `.fm__panel--md` 760px, `.fm__panel--lg` 1020px.

Behavior:
- Esc closes.
- Locks body scroll while open.
- Animates in: scale 0.96 → 1, translateY 8 → 0, opacity 0 → 1 (180ms cubic-bezier).
- Scrim fades 160ms.

### `<BookModal>` — `.fm__panel--lg`

The library/corpus selector. Anatomy, top → bottom:

#### Header — `.fm__hd.fm__hd--kpi`

A 5-tile KPI strip (`.bm-kpis` grid `auto-fit minmax(110px, 1fr)`). One tile is "accent" (the most meaningful retrieval metric):

| Tile         | Value source                                    |
|--------------|-------------------------------------------------|
| Selected     | `selected.length / indexed.length` (the `/N` part in a smaller text-tertiary "sub") |
| Chunks       | `sum(b.chunks for b in selected)` — **`.bm-kpi--accent`**, glowing |
| Figures      | `sum(b.figures for b in selected)`              |
| Chapters     | `sum(b.chapters for b in selected)`             |
| Vectors      | `1024d` (constant — embedding dimension)        |

Each tile: 1px border-subtle, radius 8, padding 12/14, with a soft diagonal gradient overlay (`::after`). Accent tile has accent border + inset accent glow + accent-colored value with text-shadow glow.

Close button (`.fm__close`) in the top-right corner.

#### Chip toggle row — `.bm-chip-row`

A row of pill-shaped chips, one per book (`.bm-chip`). Format: `[● ISLP 1,247]`.

- Default: subtle border, text-secondary.
- `.is-on`: accent-soft background (rgba(63,169,255,0.10)) + accent border + accent glow shadow + inset glow.
- `.is-pending` (book is not yet indexed): 0.55 opacity + "not indexed" sub-badge + cursor not-allowed.

Click toggles the book's `selected` state (if indexed).

Trailing hint: `"N active"` in mono.

#### Body — `.fm__body`

- If `selected.length > 0`: render `<BookCard>` × N in a grid (`auto-fill minmax(420px, 1fr)`). Each card shows cover, title (serif), subtitle (italic serif), authors (mono), edition (mono small), stats row (Chunks · Figures · Chapters with mono numbers), description (sans), and the toggle/index control.
- If `selected.length === 0`: empty state — large `∅` glyph, serif title, hint paragraph.
- If there are un-indexed books: a "NOT INDEXED" subsection with compact `<BookCard compact>` × N. Each shows a `+ Index` CTA (dashed border button) instead of an include/exclude toggle.

#### Footer — `.fm__ft`

Left: mono hint `⌘+B to open · Esc to close`.
Right: `[Apply filter]` primary button.

### `<BookCard>` — `.book-card`

```
┌─────┬──────────────────────────────────────┐
│     │ ISLP                                 │
│ cov │ An Introduction to Statistical Lear… │
│ er  │ with Applications in Python (italic) │
│ 92  │ James, Witten, Hastie, Tibshirani…   │
│  x  │ 2nd ed. · Springer · 2023            │
│ 132 │ ─────────────────────────────────    │
│     │ CHUNKS  FIGURES  CHAPTERS            │
│     │ 1,247   184      13                  │
│     │ ─────────────────────────────────    │
│     │ A modern, accessible treatment of …  │
│     │ <islp_chunks>          [● Included]  │
└─────┴──────────────────────────────────────┘
```

- Cover: 92×132 (lg) or 56×78 (compact). Drop-shadow + inner border highlight. Top-right corner pin dot at book color with glow.
- `.is-selected`: accent border + glow + 1px inset accent ring.
- `.is-pending`: 0.55 opacity, cover desaturated.
- Toggle: pill switch (`.book-card__toggle.is-on` glows accent; knob translates and recolors).

### `<SourceModal>` — `.fm__panel--md`

Opens when the user clicks any source chip in a message OR any source card in the context panel.

#### Header — `.fm__hd--source`

Top row (`.src-modal__top`): book tag · rank · score badge · chunkId code-block.
Title (h2, serif, weight 500): the section title.
Path row (`.src-modal__path`): mono breadcrumb "ISLP / ch06 / §6.2.2 · p.247".
Close button top-right.

#### Body

- `.src-modal__legend` — info banner explaining what the highlights mean ("Highlighted spans were used as the matching basis for retrieval.").
- `.src-modal__chunk` — the full chunk text. Serif, `--text-md` (17px), `line-height: 1.7`, **text-wrap: pretty**. Background `--code-surface`, border subtle. Padding 18/22.
- Inside the chunk, `<mark class="src-hl">…</mark>` spans wrap each matched substring. The highlight uses a half-height under-bar gradient (looks like a fluorescent yellow/amber underline):

  ```css
  background: linear-gradient(180deg, transparent 50%, rgba(255, 179, 107, 0.42) 50%);
  ```

  Light mode: gold `rgba(184, 134, 11, 0.35)`.

- `.src-modal__meta` — 2-column mono key/value grid: Embedding · Score (color-coded) · Chunk ID · Highlighted spans count.

#### Footer — `.fm__ft`

Left: `[Close]` button.
Right: `[Open in reader →]` (placeholder — links to a future full-page reader view; not yet designed).

#### Highlight algorithm

Given the chunk text and an array of highlight substrings, produce interleaved `[{text}, {text, hl: true}, …]`. The prototype implementation (`highlightSpans` in `modals.jsx`) does an in-order indexOf scan, merges overlapping ranges, and emits the parts. In production, prefer to receive **byte/char ranges from the backend** so you don't depend on substring matching (which fails if the chunk has been modified post-retrieval).

---

## Tweaks Panel (preview-only)

The bottom-right floating glass panel with the design knobs (theme, accent, density, font pair, user msg style, sidebar/context defaults).

**Skip this entirely in production.** Replace with a real Settings drawer (the gear icon in the topbar). The design spec calls for a right-side drawer with sections for Model · Retrieval · Display · Theme · Shortcuts.

---

Continue to → `03_interactions.md`
