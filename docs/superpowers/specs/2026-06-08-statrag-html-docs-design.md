# statRAG HTML Documentation — Design Spec

**Date:** 2026-06-08
**Status:** Design — awaiting user review
**Scope:** Robust HTML documentation for the statRAG service, extending the existing
`docs/common ground/Elements/` doc set. Deep treatment of the 4 chat modes (two diagrams
each), a new landing homepage, and a "fancy" visual restyle of the shared theme.

---

## 1. Goal

statRAG has no robust standalone documentation. The existing `docs/common ground/Elements/`
HTML set (Overview / Ingestion / Retrieval / Chat / Models / Modes) is correct but thin —
each mode page has a single conceptual pipeline diagram and a spec table.

This project:

1. Upgrades each of the 4 mode pages to **two diagrams** — an *agentic workflow* (conceptual
   stage/agent flow) and a *functions workflow* (code call-graph), plus reference tables for
   **sources, prompts, and tools**.
2. Adds a striking **landing homepage** as the doc-site front door.
3. Restyles the shared theme into a polished "Modern Dark / Cinema" look, applied site-wide
   via shared CSS (no per-page rewrite).

Non-mode pages (Overview, Ingestion, Retrieval, Chat, Models) keep their content — they are
already verified-from-code. They inherit the new visual theme for free and get broken-link
fixes only.

## 2. Decisions (locked)

| # | Decision | Choice |
|---|---|---|
| D1 | Relationship to existing docs | **Extend** the `Elements/` set (reuse generator, sidebar, render plumbing). |
| D2 | Second diagram meaning | **Code call-graph**, verified from runner source. |
| D3 | Breadth | **Modes deep, rest light-touch.** |
| D4 | Homepage | **New** `home.html` landing page, distinct from `index.html` (Overview). |
| D5 | Visual direction | **Modern Dark / Cinema**, brand accent stays statRAG **red** for app continuity. |

## 3. Source of truth

All content is hand-encoded "verified facts" extracted at build time from code — the same
discipline the current generators already use. No runtime introspection.

| Aspect | Source file(s) |
|---|---|
| Mode registry | `src/services/chat/modes.py` (`register_all_modes`, lines 139-225) |
| Tutor runner | `src/services/chat/agents/deep_tutor.py` (+ `orchestrator_workers.py`, `ow_deepagents.py`, `coverage.py`, `formula_recovery.py`, `vision.py`) |
| Q&A runner | `src/services/chat/agents/qa.py` |
| Chapter runner (facilitate/resume) | `src/services/chat/agents/chapter.py` |
| Prompts | `src/services/chat/prompts/{tutor,qa,chapter,deep_tutor}.py` |
| Output schemas | `src/services/chat/schemas/output.py` |
| Request knobs | `src/services/chat/schemas/_core.py` |

Live mode roster (`ModeId` literal, `_core.py:11`): `tutor`, `qa`, `facilitate`, `resume`.

Every new diagram and table carries a `file:line` caption. Where the documented behaviour is
known to be changing, the page says so (see §8, Q&A note).

## 4. Architecture

Three change loci, all inside `docs/common ground/Elements/`:

1. **`style.css`** (shared) — restyle to Modern Dark / Cinema. Applies to every page.
2. **`home.html`** (new, hand-authored) — landing page.
3. **`modes/_generate.py`** (extend) — per-mode dict gains `agentic`, `funcgraph`, `prompts`,
   `tools`, `sources` keys; template gains the new sections; re-run regenerates the 4 mode
   pages + modes `index.html`.
4. **`sidebar.js`** (hand-maintained) — add a "Home" entry pointing at `home.html`.

The models generator (`models/_generate.py`) is **not** edited; its pages inherit the new CSS.

### 4.1 Unit boundaries

| Unit | Responsibility | Depends on |
|---|---|---|
| `style.css` | Visual system: tokens, layout, cards, blobs, diagram wrap, tables. | Nothing (pure CSS + Google Fonts `@import`). |
| `home.html` | Landing front door: hero, bento grid, mode cards, tech strip, entry links. | `style.css`, `sidebar.js`, mermaid CDN. |
| `modes/_generate.py` | Emit the 4 mode pages + modes index from verified `MODES` data. | `style.css` (via shell), mermaid CDN. |
| `sidebar.js` | Hand-maintained nav config (all pages). | Nothing. |

## 5. Visual system (Modern Dark / Cinema)

Defined once in `style.css` as CSS custom properties.

### 5.1 Color tokens

```css
--bg-deep:      #0a0a0f;   /* gradient top */
--bg-base:      #050506;   /* gradient bottom (never pure #000) */
--bg-elevated:  #101015;   /* cards / surfaces */
--surface:      rgba(255,255,255,0.04);
--border:       rgba(255,255,255,0.08);   /* hairline */
--fg:           #EDEDEF;
--fg-muted:     #8A8F98;
--accent:       #E5484D;   /* statRAG brand red (PRIMARY) */
--accent-glow:  rgba(229,72,77,0.18);
--ok:           #3fb950;   /* verified / run / success */
--chapter:      #9b6bd6;   /* chapter-mode purple */
--radius:       16px;
--easing:       cubic-bezier(0.16, 1, 0.3, 1);
```

Color language matches the existing mermaid node styling already in the diagrams (red brand,
green verify nodes, purple chapter map). This formalizes it.

Contrast: `--fg` on `--bg-base` ≈ 17:1 (AAA); `--fg-muted` on `--bg-base` ≈ 6:1 (AA). Accent
red on dark passes 3:1 for large UI glyphs; body text never uses accent as foreground.

### 5.2 Typography

Google Fonts via `@import` in `style.css`:

```css
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');
```

- **Headings + code:** JetBrains Mono.
- **Body:** IBM Plex Sans.
- Base body 16px, line-height 1.6. Type scale: 12 / 14 / 16 / 18 / 24 / 32 / 48.
- `font-display: swap` (via the import) to avoid FOIT.

### 5.3 Effects & motion

- Page background: `linear-gradient(180deg, var(--bg-deep), var(--bg-base))`.
- 2–3 absolute **ambient glow blobs** (radial, `filter: blur(60px)`, opacity 0.10), slow CSS
  keyframe oscillation. Wrapped in `@media (prefers-reduced-motion: reduce)` → animation off,
  blobs remain static (decoration only, no information lost).
- Cards: `--bg-elevated`, hairline border, `border-radius: var(--radius)`, subtle top-edge
  highlight (`box-shadow: inset 0 1px 0 rgba(255,255,255,.06)`), hover lift via
  `transform: translateY(-2px)` + accent-glow shadow. Transitions 150–300ms, `--easing`.
- Animate only `transform`/`opacity` (no width/height/top/left).
- `cursor: pointer` on all clickable cards/links. Visible focus ring (2px accent) for keyboard nav.

## 6. Homepage (`home.html`)

Hand-authored static page. Section order (Bento Showcase + Feature-Rich hybrid):

1. **Hero** — `statRAG` wordmark (JetBrains Mono), one-line value prop ("Local-first hybrid
   RAG over OCR'd statistics textbooks"), `current-state · verified from code` pill, ambient
   blobs behind. Primary entry button → Overview; secondary → Modes.
2. **End-to-end bento** — a wide bento grid: one large cell holds the existing end-to-end
   mermaid flow (Book → Ingestion → Qdrant → Retrieval → Chat → Answer); smaller cells call
   out hybrid retrieval (dense+BM25+RRF), per-field collections, deep-tutor pipeline.
3. **Mode cards** — 4 cards (Tutor / Q&A / Facilitate / Resume), each: icon, one-line purpose,
   architecture pill, link to the mode page. Colors: search modes red-edged, chapter modes
   purple-edged.
4. **Tech-spec strip** — compact row: Qdrant 1.12.4, `text-embedding-3-large` (3072d), nano
   default chat LLM, BM25 sparse, Python 3.12. (Mirrors Overview Stack table, condensed.)
5. **Entry links** — cards linking to Overview, Ingestion, Retrieval, Chat & deep-tutor,
   Models, Modes.

No forms, no email capture, no fake social proof (rejected the generic "Newsletter" pattern
the design-system tool guessed). This is internal technical documentation.

## 7. Mode pages (the deep treatment)

Per-mode page layout (generated by `modes/_generate.py`):

1. Header + "What it serves" — *existing.*
2. **Agentic workflow** — conceptual stage/agent flow. *(Current `diagram`, relabeled `agentic`.)*
3. **Functions workflow** — NEW mermaid call-graph: entrypoint function → each stage's Python
   function, with edges to the prompt constant, tool/retrieval call, and source module each
   stage invokes. Node color convention: LLM-call functions green, prompt constants purple,
   tool/retrieval calls red.
4. **Sources, prompts & tools** — NEW. Three tables:
   - **Prompts:** constant name → `file:line` → role.
   - **Tools / retrieval calls:** function → what it hits (Qdrant collection / reranker / LLM tier).
   - **Source modules:** stage → `path:line`.
5. Spec table — *existing.*
6. Output fields — *existing.*
7. Chapter knobs — *existing, facilitate/resume only.*

### 7.1 Per-mode functions-graph content

- **tutor** → `deep_tutor.py` chain: query-planner fn → multi-query retrieval/RRF → density +
  author-diversity + rerank → coverage-check loop → figure-judge → orchestrator-workers
  (`orchestrator_workers.py` / `ow_deepagents.py`) → draft/synthesis → formula-recovery →
  vision-explain → `TutorAnswer`. Each node tagged with its `prompts/deep_tutor.py` constant
  and relevant `TUTOR_*` env flag.
- **qa** → `qa.py` four node functions: `scope → retrieve → generate → verify`, with the
  schema-repair retry edge on `generate` (ADR-005) and `prompts/qa.py` constants.
- **facilitate / resume** → shared `chapter.py` call-graph:
  `parse-scope → fetch-chapter → resolve-subtopics → map → stitch → ground → ChapterDigest`.
  Only the map-prompt node differs (`CHAPTER_MAP_FACILITATE_PROMPT` vs `CHAPTER_MAP_RESUME_PROMPT`).

### 7.2 Generator template guards

New sections render only when their key is present (same pattern as the existing
`chapter_knobs` guard). A mode dict missing `funcgraph`/`prompts`/`tools` omits that section
rather than emitting an empty block.

## 8. Known-changing behaviour

The Q&A mode page documents the **current live** 4-node graph (`scope → retrieve → generate →
verify`). A scoped agentic-retrieval deepagent rebuild is specified but **not started**
(CLAUDE.md pending task; `docs/superpowers/specs/2026-06-05-qa-deepagent-design.md`). The Q&A
page carries a one-line note linking that spec so the doc never claims the unbuilt design.

## 9. Error handling

- Mermaid render already has try/catch in the shared render script → renders parse errors in
  amber `<pre>` instead of breaking the page. Each new graph is validated to render before the
  work is called done.
- Generator is pure string templating; missing optional keys degrade gracefully (§7.2).
- Reduced-motion: blobs/hover animations disabled under `prefers-reduced-motion`; no content
  depends on motion.

## 10. Testing / verification

Static files opened via `file://` in Chrome (no server needed):

1. Run `cd "docs/common ground/Elements/modes" && python3 _generate.py`; confirm it writes
   `index.html` + 4 mode pages with no error.
2. Open `home.html` and the 4 mode pages in Chrome. Verify:
   - Both diagrams on each mode page render as **SVG** (not raw mermaid text or amber error).
   - New sources/prompts/tools tables populate.
   - Bento grid + mode cards render; ambient blobs animate; hover-lift works.
   - Sidebar nav (incl. new Home entry) and all cross-page links resolve.
3. Toggle OS reduced-motion → confirm blobs/animations stop, layout intact.
4. Spot-check 2–3 cited `file:line` references against the actual source.
5. Resize to 1440 / 1024 / 768 / 375 → no horizontal scroll, cards reflow/stack.

## 11. Out of scope

- Rewriting Overview / Ingestion / Retrieval / Chat / Models page **content** (theme-only uplift).
- Documenting the unbuilt Q&A deepagent (noted, not described).
- Any change to `src/` code, the live web app, or build config.
- A static-site generator or framework — these stay hand-authored + the two Python generators.

## 12. Deliverables

- Restyled `docs/common ground/Elements/style.css`.
- New `docs/common ground/Elements/home.html`.
- Extended `docs/common ground/Elements/modes/_generate.py` + the 4 regenerated mode pages and
  modes `index.html`.
- Updated `docs/common ground/Elements/sidebar.js` (Home entry).
- Verified-in-Chrome screenshots / confirmation per §10.
