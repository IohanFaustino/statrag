# statrag — Design Handoff

> A research-grade RAG chat interface over statistical/econometric textbooks. This package is the design reference for implementation in a real codebase.

---

## ⚠️ About These Files

The HTML/JSX/CSS files in `design/` are **design references**, not production code. They are prototypes built to demonstrate look, behavior, and component anatomy. **Do not ship them as-is.**

Your job is to **recreate these designs in the target codebase's environment**:
- If the project already uses React + Next.js / Vite / Remix → use that.
- If there is no codebase yet → React + Vite + TypeScript + CSS Modules (or Tailwind) is the safe default. The design's architecture is React-functional-with-hooks, no opinionated state library, no router.
- Backend: the design assumes an HTTP/SSE backend with Qdrant for vector retrieval, an LLM (OpenAI or DeepSeek), and KaTeX/MathJax for math rendering. See `05_rag_pipeline.md` for the implied service contract.

---

## Fidelity

**High-fidelity (hifi).** Pixel-perfect — colors, typography, spacing, borders, glow shadows, and timings are all final. Reproduce 1:1. The visual system is unusual (glassmorphism + neon-blue accents in dark, financial navy-on-paper in light) and is a deliberate brand expression — do not substitute it with a generic design system.

The only intentional placeholders are:
- Book covers (stylized SVG) — replace with real cover imagery when available
- Figure thumbnails (stylized SVG mini-charts) — replace with rendered matplotlib/Manim figures from the corpus
- Sample conversation content — replace with live RAG output

Everything else (typography scale, color tokens, component anatomy, motion, layout grid) is hifi.

---

## What's In This Folder

```
design_handoff_statrag/
├── README.md                  ← this file (start here)
├── 01_design_tokens.md        ← colors, type, spacing, shadows, motion
├── 02_components.md           ← every component, with anatomy + states
├── 03_interactions.md         ← flows, animations, keyboard, responsive
├── 04_data_model.md           ← TypeScript types + state shape
├── 05_rag_pipeline.md         ← backend contract + RAG implementation notes
└── design/                    ← the working HTML prototype (open statrag.html)
    ├── statrag.html
    ├── styles.css             ← base CSS (layout, tokens, components)
    ├── neon.css               ← neon/glass overlay + light financial theme
    ├── icons.jsx              ← stroke icon set
    ├── shell.jsx              ← Topbar, Sidebar, ContextPanel
    ├── chat.jsx               ← MessageThread, InputBar, ModelPicker, TempChat
    ├── modals.jsx             ← FocusModal, BookModal, SourceModal, BookCover
    ├── app.jsx                ← composition + state + tweaks wiring
    ├── data.js                ← all mock data (books, sources, thread, models)
    └── tweaks-panel.jsx       ← preview-only tweaks UI (skip in production)
```

Open `design/statrag.html` in a browser to see the live prototype. All the documentation below references components and CSS classes you can inspect there.

---

## Aesthetic Direction

**Concept**: "The Scholar's Terminal" — a dark, typographically rich interface that feels like a high-end scientific notebook crossed with a Unix terminal. Dense, purposeful, precise. The light mode shifts the metaphor to a **financial broker terminal**: warm paper, deep navy, gold highlights.

**Mood (dark)**: glass + cosmic ambient + electric blue neon glow.
**Mood (light)**: cream paper, navy serif text, subtle gold accents.

**NOT**:
- Generic ChatGPT-style white bubbles
- Material/iOS standard components
- Purple gradients, rounded-everything softness
- Stock illustrations or emoji-as-accent

---

## High-level Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ TOPBAR (48px)  [≡ logo]  [breadcrumb]   [Books ▾][theme][⚙ ·]  │
├──────────┬──────────────────────────────┬───────────────────────┤
│          │                              │                       │
│ SIDEBAR  │    MAIN CHAT AREA            │   CONTEXT PANEL       │
│ (260px)  │    (fluid center, max-720)   │   (320px)             │
│          │                              │                       │
│ • New    │  ╔══════════════════════╗    │  SOURCES (4)          │
│ • Hist   │  ║ User bubble (right)  ║    │  [cards…]             │
│ • Roads  │  ╚══════════════════════╝    │                       │
│          │                              │  FIGURES (2)          │
│          │  ▸ TUTOR MODE · ISLP+HANS    │  [cards…]             │
│          │    Assistant body text…      │                       │
│          │    [math block]              │  ▸ Retrieval (acc.)   │
│          │    [source chips]            │                       │
│          │                              │                       │
│          │  ┌────────────────────────┐  │                       │
│          │  │ Input area + toolbar   │  │                       │
│          │  └────────────────────────┘  │                       │
└──────────┴──────────────────────────────┴───────────────────────┘
```

Three-column at `>1280px`, two-column (no context panel) at `768–1280px`, single column at `<768px`.

When the user opens a temporary side chat, the **main column splits into two side-by-side panes** (primary + temp). The temp pane has a tinted purple/lilac background to signal its disposable nature.

---

## Screens / Views

There are six distinct surfaces. Component anatomy for each is in `02_components.md`.

1. **Default chat** — the resting state. Mid-conversation, three panes visible.
2. **BookModal** — focus modal for selecting which Qdrant collections to query. KPI strip + chip toggle row + active book cards + "not indexed" section.
3. **SourceModal** — focus modal showing the full retrieved chunk with the matching span highlighted (amber underline in dark, gold in light).
4. **ModelPicker popover** — anchored to the input bar; groups models by provider (OpenAI, DeepSeek), each row showing tagline / context window / cost tier / speed badge.
5. **Temporary side-by-side chat** — opened by hovering an assistant message and clicking the `+` button that appears on its right edge. The chat splits horizontally; the temp pane is purposely tinted.
6. **Light "financial" theme** — same layout, swapped palette: cream `#F2EEE5` background, deep navy `#001F3F` text + accent, gold `#B8860B` highlights, navy radial backdrop instead of cosmic blue.

---

## Implementation Order (suggested)

If you're building this in a real app, take it in this order — each phase produces something demoable:

1. **Tokens + layout shell** — design tokens (CSS vars or your token system), the topbar/sidebar/main/context grid, basic glass surfaces. No data yet.
2. **Static chat thread** — render the canned conversation (user bubbles + assistant doc) with KaTeX. No backend, no streaming.
3. **Right context panel** — sources cards + figure cards + retrieval metadata accordion, fed from the same canned data.
4. **BookModal + SourceModal + theme toggle** — focus modal pattern, KPI/chip row, full chunk + highlight render. Wire keyboard (Esc, ⌘B).
5. **Real backend** — wire `POST /chat` (SSE streaming) and `POST /search`. Replace canned data. See `05_rag_pipeline.md`.
6. **Mode picker + Model picker + Hover-fork temp chat** — the secondary UI surfaces.
7. **Remaining modes** — Compare, Figures, Quiz, Navigate, Prereqs, Annotate, Research, Math, Path, Roadmap. Only Tutor is fully designed; the others are pickable but have not had their output views designed yet (flag a follow-up design pass).

---

## Conventions

- **All design tokens in CSS custom properties.** Light/dark are `:root[data-theme="dark|light"]` overrides. Theme toggle flips the attribute; the entire palette reflows.
- **No icon library.** All icons are inline SVG, 16×16 viewBox, 1.4 stroke, currentColor. Copy from `design/icons.jsx`.
- **Inter-component spacing comes from CSS gap on flex/grid containers, not margins on children.** Maintain this — it survives drag-reorder and conditional rendering cleanly.
- **Glass surfaces:** `backdrop-filter: blur(14–22px) saturate(160–170%)` over a semi-transparent background (alpha 0.3–0.55). Always include a `-webkit-` prefix for Safari.
- **Reduced motion is respected.** `@media (prefers-reduced-motion)` collapses all transitions to ~0ms.

---

## Open Questions to Resolve with the User Before Building

1. **Stack confirmation.** React? Next.js (app router) vs Vite? Server components? CSS modules vs Tailwind vs vanilla? The design is framework-agnostic but the choice affects component file shape.
2. **Auth model.** Designs assume single-user local-first. Multi-user / SSO needs sidebar conversation history scoping + per-user model defaults.
3. **Persistence layer.** Conversations + saved roadmaps need somewhere to live. SQLite + localStorage? Postgres + server?
4. **Streaming protocol.** SSE vs WebSocket. SSE is recommended (simpler, plays well with HTTP).
5. **The "Modes" beyond Tutor.** Compare / Quiz / Roadmap etc. have been picked-out in the mode menu but their output views are not yet designed. Confirm scope.
6. **KaTeX vs MathJax.** Design uses KaTeX (fast, smaller). Confirm acceptable.
7. **Real book corpus.** Which textbooks are actually indexed? The design ships ISLP + Hansen as active and ESL + Wooldridge as "not yet indexed."

---

Continue to → `01_design_tokens.md`
