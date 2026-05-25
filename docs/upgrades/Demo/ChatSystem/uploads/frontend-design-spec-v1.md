# Frontend Design Specification
## RAG Chat System — Statistical Textbooks

> A design brief for a local-first, research-grade conversational interface over a hybrid RAG pipeline. The aesthetic must feel like a premium academic tool — not a generic chatbot wrapper.

---

## Aesthetic Direction

**Concept**: *"The Scholar's Terminal"* — a dark, typographically rich interface that feels like a high-end scientific notebook crossed with a Unix terminal. Dense, purposeful, and precise. No decorative elements that don't carry information.

**Mood**: Dark academia meets computational tool. Think: editorial scientific journal rendered in dark mode. Every pixel justifies its existence.

**References**: Linear.app's density + Obsidian's editorial feel + a monospaced academic paper.

**NOT**: A generic ChatGPT-style white bubble interface. No gradients on gradients. No rounded-everything softness. No purple.

---

## Color Palette

```
Background primary:   #0D0F12   (near-black, slightly warm)
Background secondary: #13161B   (panels, sidebars)
Background tertiary:  #1A1E25   (cards, input areas, hover states)
Background elevated:  #21262F   (modals, dropdowns, tooltips)

Border subtle:        #2A2F3A   (dividers, card outlines)
Border default:       #3A404E   (active borders, focus rings)

Text primary:         #E8ECF0   (main readable text)
Text secondary:       #8B95A5   (metadata, labels, timestamps)
Text tertiary:        #5A6270   (placeholders, disabled)
Text inverse:         #0D0F12   (text on light accent backgrounds)

Accent primary:       #4F9CF9   (interactive elements, links, selected mode)
Accent secondary:     #7EC8A4   (success states, ISLP book color)
Accent tertiary:      #E8A87C   (Hansen book color, warnings)
Accent danger:        #E86C6C   (errors, contradicts stance)
Accent neutral:       #9B8FCC   (figure references, image indicators)

Code / math surface:  #111419   (KaTeX blocks, code snippets)
Code accent:          #4F9CF9   (math operators, LaTeX highlights)

Syntax amber:         #F0C060   (section titles in source citations)
```

---

## Typography

**Display / Headings**: `IBM Plex Serif` — academic, editorial, distinctive. Used for section headers, mode titles, roadmap scene titles.

**Body / UI**: `IBM Plex Sans` — clean, engineered feel. Used for all prose answers, labels, metadata.

**Monospace / Math**: `IBM Plex Mono` — code blocks, LaTeX source, source citations, metadata values.

**Scale**:
```
--text-xs:   11px / 1.4  (metadata, timestamps, labels)
--text-sm:   13px / 1.5  (secondary UI, captions)
--text-base: 15px / 1.65 (body text, answers)
--text-md:   17px / 1.6  (section headers, questions)
--text-lg:   21px / 1.4  (mode titles, prominent labels)
--text-xl:   28px / 1.2  (display, roadmap scene numbers)
--text-2xl:  38px / 1.1  (hero elements, empty states)
```

---

## Layout Structure

### Global Shell

```
┌─────────────────────────────────────────────────────────────────┐
│ TOPBAR (48px)                                                   │
│ [≡ Logo]  [Mode pills]                    [Book filter] [⚙ ···] │
├──────────────┬──────────────────────────────┬───────────────────┤
│              │                              │                   │
│  SIDEBAR     │    MAIN CHAT AREA            │   CONTEXT PANEL   │
│  (260px)     │    (fluid center)            │   (320px)         │
│              │                              │                   │
│  Conversation│    Message thread            │   Retrieved       │
│  history     │                              │   sources         │
│              │                              │                   │
│  ─────────   │    ─────────────────────     │   Figures         │
│              │                              │                   │
│  Saved       │    Input bar (bottom)        │   Score           │
│  roadmaps    │                              │   indicators      │
│              │                              │                   │
└──────────────┴──────────────────────────────┴───────────────────┘
```

**Responsive**:
- `> 1280px`: Three-column (sidebar + chat + context panel)
- `768–1280px`: Two-column (sidebar collapsed to icon rail + chat; context panel slides in on demand)
- `< 768px`: Single column; sidebar and context panel become bottom sheets

---

## Topbar

**Height**: 48px, `background: var(--bg-secondary)`, `border-bottom: 1px solid var(--border-subtle)`

**Left**: Compact logo — a small geometric mark (two overlapping document shapes, one with a vector arrow) + wordmark "statrag" in `IBM Plex Mono`, weight 500, `--text-secondary`.

**Center**: **Mode Pills** — the primary navigation element. A horizontal pill group, not tabs. Each pill:
- 32px height, 12px horizontal padding
- Icon (16px, stroke-based) + short label
- Inactive: `bg: transparent`, `color: --text-secondary`, `border: 1px solid transparent`
- Active: `bg: --bg-tertiary`, `color: --text-primary`, `border: 1px solid --border-default`, left accent bar `3px solid --accent-primary`
- Transition: `120ms ease` color + background on hover/select
- On hover (inactive): `bg: --bg-tertiary`, `color: --text-primary`

**Pill order**:
```
📖 Tutor  |  🔀 Compare  |  🖼 Figures  |  📝 Quiz  |  🔍 Navigate
🗺 Prereqs  |  ✍ Annotate  |  🔬 Research  |  ∑ Math  |  📅 Path  |  🎬 Roadmap
```

Consider collapsing to a dropdown "More ▾" after the 5th pill on narrower viewports.

**Right**:
- `Book:` dropdown — `ALL · ISLP · Hansen` with colored dots (green for ISLP, amber for Hansen)
- Separator
- Settings gear icon (opens a right-side drawer)
- Status dot — animated pulse when Qdrant is live; grey when offline

---

## Left Sidebar

**Width**: 260px, `background: var(--bg-secondary)`, `border-right: 1px solid var(--border-subtle)`

### Sections

**"New conversation" button**: Full-width, 36px, `border: 1px dashed var(--border-default)`, `color: --text-secondary`. On hover: border becomes solid, `color: --accent-primary`. Icon: `+` with a subtle spark.

**Conversation history**: Grouped by recency (Today / Yesterday / This week / Earlier). Each item:
- 36px height, 12px left padding
- Truncated title in `--text-sm`
- On hover: `bg: --bg-tertiary`, reveal mode icon on right
- Active conversation: `bg: --bg-tertiary`, left border `2px solid --accent-primary`
- Right-click or `···` reveals: Rename / Delete / Export

**Saved Roadmaps section** (below a divider):
- Header: `ROADMAPS` in `--text-xs`, `--text-tertiary`, letter-spacing `0.12em`
- List items show topic title + scene count badge + date
- Clicking opens the roadmap in a full-width view overlay, not the chat

**Collapse button** at bottom: chevron icon, collapses sidebar to 52px icon rail showing only conversation count badge and new button.

---

## Main Chat Area

### Message Thread

**Container**: `max-width: 720px`, centered, `padding: 24px 0`, `overflow-y: auto`

**Scroll behavior**: Smooth auto-scroll on new messages. A "↓ New messages" floating chip appears if user has scrolled up.

#### User Message Bubble

```
                              ┌─────────────────────────────┐
                              │ How does Ridge regression   │
                              │ differ from OLS in          │
                              │ Hansen's treatment?         │
                              └─────────────────────────────┘
                                                      [you] · 14:32
```

- Right-aligned
- `bg: --bg-elevated`, `border: 1px solid --border-default`
- `border-radius: 12px 12px 2px 12px`
- `padding: 12px 16px`
- `max-width: 480px`
- Text in `--text-base`, `--text-primary`

#### Assistant Message

Left-aligned, no background bubble — answer renders directly on the page background, giving it a "document" feel rather than a "chat" feel.

```
  [mode icon]  TUTOR MODE  ·  ISLP + HANSEN  ·  3 sources  ·  0.8s

  Ridge regression extends OLS by adding an L2 penalty term to
  the loss function...

  ┌─────────────────────────┐
  │  β̂_ridge = argmin ...  │   ← KaTeX rendered block
  │  ‖y − Xβ‖² + λ‖β‖²    │
  └─────────────────────────┘

  Hansen (ch07, §7.4) frames this as a *shrinkage estimator*,
  emphasizing the bias-variance tradeoff, while ISLP (ch06,
  §6.2) approaches it from a model selection perspective...

  [📖 Hansen ch07] [📖 ISLP ch06]   ← Source chips
```

**Answer anatomy**:
- **Mode badge**: small pill top-left — mode icon + mode name + books queried + source count + latency. `--text-xs`, `--text-tertiary`
- **Body text**: `IBM Plex Sans`, `--text-base`, `line-height: 1.65`
- **Inline math**: KaTeX, styled to match text size. Operators in `--code-accent`
- **Math blocks**: full-width code surface `bg: --code-surface`, `border: 1px solid --border-subtle`, `border-radius: 6px`, `padding: 16px 20px`
- **Source chips**: small inline tags below the answer, `bg: --bg-elevated`, `border: 1px solid --border-subtle`, book name + chapter. Clicking a chip highlights the corresponding card in the right Context Panel
- **Figures**: if figure-aware mode is active, figures appear as inline cards with caption below (see Figure Card spec)

#### Streaming behavior

Text streams in word-by-word. A subtle blinking cursor `|` appears at the end during generation. Source chips and figure cards fade in after streaming completes (300ms fade).

---

## Input Bar

**Position**: Sticky bottom of chat area, `background: --bg-primary` with `box-shadow: 0 -1px 0 var(--border-subtle)`.

```
┌──────────────────────────────────────────────────────────┬──────┐
│  Ask anything about statistics...                        │  ↑   │
│                                                          │      │
│  [📎 Attach]  [∑ Math]  [🎬 Mode: Tutor ▾]              │      │
└──────────────────────────────────────────────────────────┴──────┘
```

**Textarea**: Auto-expanding, min 48px, max 200px. `bg: --bg-tertiary`, `border: 1px solid --border-subtle`, `border-radius: 10px`. On focus: `border-color: --accent-primary`, subtle `box-shadow: 0 0 0 2px rgba(79,156,249,0.15)`.

**Toolbar (below textarea)**:
- `📎 Attach` — opens file picker (for annotate and research modes; accepts `.md`, `.txt`, `.pdf`)
- `∑ Math` — toggles a small LaTeX input helper overlay
- `Mode indicator` — compact pill showing current mode; clicking opens a mode-switch popover (same pills as topbar, but in a floating card)

**Send button**: 40px×40px, `bg: --accent-primary`, `border-radius: 8px`, arrow-up icon. Disabled state: `bg: --bg-elevated`, `color: --text-tertiary`. On hover (enabled): `bg: #6AADFF` + subtle scale `1.02`.

**Keyboard shortcuts**: `Enter` to send, `Shift+Enter` for newline. `Cmd+K` opens mode switcher.

---

## Right Context Panel

**Width**: 320px, `background: var(--bg-secondary)`, `border-left: 1px solid var(--border-subtle)`

Appears automatically after the first assistant message. Can be collapsed to 0 with an arrow button on its left edge.

### Sections

#### Retrieved Sources

Header: `SOURCES (3)` in `--text-xs` label style.

Each source card:
```
┌─────────────────────────────────────────┐
│ 🟢 ISLP                        #1  0.94 │
│ Chapter 6 · §6.2.1                      │
│ Ridge Regression                        │
│ "...the penalty term λΣβj² shrinks..."  │
└─────────────────────────────────────────┘
```
- `bg: --bg-tertiary`, `border: 1px solid --border-subtle`, `border-radius: 8px`, `padding: 12px`
- Rank badge (`#1`, `#2`...) top-right, `--text-xs`, `--text-tertiary`
- Relevance score: small number `0.00–1.00`, color-coded: green >0.8, amber 0.6–0.8, red <0.6
- Book color dot: green (ISLP) or amber (Hansen)
- Section path in `--text-xs`, `--text-secondary`
- Section title in `--text-sm`, `--text-primary`, `font-weight: 500`
- Excerpt: 2 lines truncated, `--text-xs`, `--text-secondary`, `font-style: italic`
- On hover: border becomes `--border-default`; `cursor: pointer` — clicking expands to show full chunk in a modal

#### Figure Cards (when figure-aware or math mode)

```
┌─────────────────────────────────────────┐
│ 🟣 Figure                               │
│ ISLP · ch06 · fig_6_4                   │
│ ┌───────────────────────────────────┐   │
│ │         [figure thumbnail]        │   │
│ └───────────────────────────────────┘   │
│ "Bias-variance tradeoff as λ varies"    │
└─────────────────────────────────────────┘
```

- Thumbnail: `border-radius: 4px`, `bg: #000`, `aspect-ratio: 4/3`, `object-fit: contain`
- Caption below in `--text-xs`, `--text-secondary`
- Click: opens figure in a full-screen lightbox with caption and section context

#### Retrieval Metadata (collapsed by default)

Expandable accordion at the bottom of the panel:
- Query used for retrieval (after rewriting)
- Embedding model
- Retrieval time (ms)
- Collections queried
- Filter applied (book/theme)

---

## Mode-Specific Views

### Quiz Mode Output

Instead of a chat bubble, quiz output renders as a dedicated card deck:

```
┌─────────────────────────────────────────────────────────────┐
│  QUIZ · ISLP ch06 · 4 questions · Medium difficulty         │
├─────────────────────────────────────────────────────────────┤
│  Q1 of 4                                          [→ Skip]  │
│                                                             │
│  What is the effect of increasing λ in Ridge               │
│  regression on the magnitude of coefficients?              │
│                                                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│  │ A. They │  │ B. They │  │ C. They │  │ D. No   │       │
│  │ grow    │  │ shrink  │  │ become  │  │ change  │       │
│  │         │  │         │  │ binary  │  │         │       │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘       │
│                                                             │
│                          [Show Hint]  [Reveal Answer]       │
└─────────────────────────────────────────────────────────────┘
```

Answer options: 4-up grid, each option a pressable card. Selected state: `border: 1px solid --accent-primary`, `bg: rgba(79,156,249,0.08)`. Correct after reveal: green border. Incorrect: red border.

Progress bar at top of card: thin `4px` line, `bg: --accent-primary`, animated width.

### Roadmap Mode Output

Full-width, replaces the chat thread layout for this response. Renders as a vertical scene list:

```
┌─────────────────────────────────────────────────────────────┐
│  🎬 ROADMAP: Bias-Variance Tradeoff                         │
│  11 scenes · est. 18 min · ISLP ch02 + Hansen ch05         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  01                                                         │
│  ─────────────────────────────────────────────             │
│  The Prediction Error Problem                               │
│  ISLP · ch02 · §2.2                                        │
│                                                             │
│  Concept ···· Why models fail on unseen data               │
│  Visual ····· Animated scatter plot + overfitting curve     │
│  Tool ········ Manim: Axes + Dot objects + Transform        │
│  Duration ··· ~90s                                          │
│                                                             │
│  [🖼 fig_2_12]                                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
│  [📋 Copy YAML]  [💾 Save Roadmap]  [🔄 Regenerate]        │
└─────────────────────────────────────────────────────────────┘
```

Scene number: `--text-2xl`, `IBM Plex Serif`, `font-weight: 300`, `--text-tertiary` — large, editorial.
Scene title: `--text-lg`, `IBM Plex Serif`, `font-weight: 500`.
Metadata rows: dot-leader layout (`Concept ····· value`), `IBM Plex Mono`, `--text-sm`.

### Prereq Tracer / Study Path Output

Renders a visual dependency graph (SVG-based). Nodes are sections, edges are prerequisite relationships. Layout: top-down DAG.

Node states:
- Completed: filled circle, `--accent-secondary` (green)
- Current target: pulsing ring, `--accent-primary` (blue)
- Required prereq: outlined circle, `--accent-tertiary` (amber)
- Optional: dashed outline, `--text-tertiary`

Clicking a node expands a popover with section title, book, chapter, and a "Read" button.

### Research Assistant / Annotated Reading Output

A split-panel within the main chat area:

```
┌──────────────────────┬──────────────────────────────────────┐
│  YOUR TEXT           │  ANALYSIS                            │
│                      │                                      │
│  "Ridge regression   │  📗 BACKGROUND                       │
│  adds an L2 penalty  │  ISLP ch06 §6.2 — provides           │
│  to shrink           │  foundational treatment              │
│  coefficients..."    │                                      │
│        ↑             │  ✅ SUPPORTS                         │
│  [highlighted term]  │  Hansen ch07 §7.4 — confirms         │
│                      │  shrinkage interpretation            │
└──────────────────────┴──────────────────────────────────────┘
```

Highlighted terms: underlined with color matching stance (green = supports, amber = background, red = contradicts). Clicking a highlight scrolls the right panel to the corresponding analysis entry.

---

## Micro-interactions & Motion

**Guiding principle**: Motion serves comprehension, never decoration. All animations under 200ms unless communicating a process.

| Element | Animation | Duration | Easing |
|---|---|---|---|
| Mode switch | Cross-fade content + slide active pill indicator | 150ms | ease-out |
| Message stream | Word-by-word fade-in in batches | continuous | linear |
| Source card hover | border-color + translate-y(-1px) | 100ms | ease |
| Context panel open | slide-in from right | 200ms | ease-out |
| Figure lightbox | scale(0.95)→scale(1) + fade | 180ms | ease-out |
| Quiz answer select | scale(0.98)→scale(1) + border flash | 120ms | ease |
| Roadmap scene reveal | staggered fade-up per scene (50ms delay each) | 200ms | ease-out |
| DAG node expand | radial scale from node center | 200ms | spring |
| Relevance score | count-up animation on first render | 600ms | ease-out |
| Send button press | scale(0.95) + brief bg darken | 80ms | ease |

**Loading states**:
- Initial retrieval: three animated dots in the mode badge area, `--text-tertiary`
- Streaming: blinking cursor at end of text
- Figure loading: skeleton with shimmer animation, exact card dimensions

---

## Empty States

**New conversation**:
```
          ∑ statrag

   What do you want to understand?

   [📖 Explain a concept]   [🔍 Find a section]
   [🎬 Plan a video]        [📝 Generate a quiz]

   Tip: Press Cmd+K to switch modes
```

Center-aligned, `--text-2xl` for the glyph. Suggestion chips are pressable and pre-fill the input.

---

## Settings Drawer

Slides in from the right at 360px width. Sections:

- **Model**: dropdown `GPT / DeepSeek`, with cost indicator per model
- **Retrieval**: sliders for top-K (default 5), score threshold (default 0.6), toggle sparse/dense/hybrid
- **Display**: toggle math rendering on/off, figure display on/off, source panel always-visible / auto-hide
- **Theme**: Dark (default) / Light / System
- **Shortcuts**: reference card (read-only)

---

## Accessibility

- All interactive elements reachable by keyboard; visible focus rings using `--accent-primary` outline
- Mode pills announce mode change via `aria-live` region
- KaTeX blocks include `aria-label` with human-readable equation description
- Color is never the only signal (stance classification uses icon + text, not just color)
- Minimum contrast ratio 4.5:1 for all body text
- Reduced motion: all transitions collapse to instant when `prefers-reduced-motion: reduce`

---

## Tech Stack Notes

- **Framework**: React (functional + hooks)
- **Math rendering**: KaTeX (client-side)
- **Styling**: CSS custom properties for all tokens; component-scoped CSS modules
- **DAG graph**: D3.js or `@visx/network`
- **Streaming**: SSE or `fetch` with `ReadableStream`
- **Figure lightbox**: custom portal + focus trap
- **Animations**: CSS transitions + `@keyframes`; Framer Motion only for DAG and roadmap stagger

---

*Design spec v1.0 — RAG Chat System Part 2 · For use with Claude design generation*
