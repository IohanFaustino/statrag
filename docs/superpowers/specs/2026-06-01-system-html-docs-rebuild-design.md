# Design — Rebuild the system HTML documentation from zero

**Date:** 2026-06-01
**Status:** approved-pending-review
**Owner:** rebuild of `docs/common ground/Elements/`

## Problem

The HTML documentation of the system is no longer trusted. The single page
`docs/common ground/Elements/index.html` ("Common ground — Orchestrator-Workers")
grew organically: §1–§17 are dated change-log entries layered on top of each
other, narrowly framed around the orchestrator-workers pattern. It reads as a
history of edits, not a current-state picture of the system, and is assumed to
have drifted from the actual code. `report.html` is a one-off audit from
2026-05-21, also stale.

Goal: wipe `docs/common ground/Elements/` and rebuild it **from inspection of
the actual code**, treating prior docs (HTML *and* markdown) as hints to verify,
never as truth.

## Decisions (from brainstorming)

- **Scope:** rebuild the entire `docs/common ground/Elements/` directory.
- **Altitude:** whole system, current-state — ingestion → retrieval →
  chat/deep-tutor — as it actually is now. No dated changelog narrative (that
  lives in `docs/system/changelog.md`).
- **Format:** multi-page (one HTML file per layer + a landing page + an audit).
- **report.html:** replaced with a fresh verification audit produced during this
  rebuild.
- **Rigor:** full per-page verification — inspect code first, record a
  claim→`file:line`→verdict matrix in `report.html`, then write each page from
  verified facts.

## Deliverable — page set

All under `docs/common ground/Elements/`:

| File | Responsibility |
|---|---|
| `index.html` | Landing/overview. System at a glance; the 3-layer Chinese wall (`src/core` / `src/ingestion` / `src/services`); stack table; one cross-cutting flow diagram (book → ingest → Qdrant → retrieval → chat answer); nav to the other pages. |
| `ingestion.html` | Ingestion **task**. Pipeline: preprocess (`processed/*_preproc.py`) → `regex_pass` → `llm_enrich` → `build_documents` → embed → Qdrant upsert. Per-field collections (`<field>_textbooks` + `<field>_images`), book yaml config, enrichment provider (DeepSeek v4-flash) vs embeddings/captioning (OpenAI). |
| `retrieval.html` | Retrieval **service**. Hybrid dense + sparse (bm25) → RRF fusion → density select → cross-encoder rerank → author diversity; the separate image-density path. |
| `chat.html` | Chat **service** + the **deep-tutor pipeline** (the large DAG). Modes (tutor / qa / chapter / facilitate / resume); SSE + detached resumable runs; LLM providers + router; the full stage graph — query planner → multi-query retrieval + RRF → density + diversity + rerank → coverage check → figure judge → planner-orchestrator → drafting workflow {single / organize / orchestrator-workers} → vision explain — with the `TUTOR_*` knobs. The orchestrator-workers framing lives **only** here. |
| `report.html` | Verification audit. A matrix: claim → `file:line` anchor → verdict (verified / drift / removed). Built as the pages are written, so the documentation is self-auditing and demonstrably from inspection. |

## Shared chrome

- **`style.css`** — one shared stylesheet. Extract the existing dark theme
  (CSS custom props: `--bg #0b0c0e`, `--panel`, `--accent #E5484D` red, `--ok`,
  `--warn`, etc.), card / table / verdict / pill classes. Single edit re-themes
  every page.
- **Top nav** — a consistent nav bar on every page linking the 5 pages, with the
  current page marked active. Plain relative `<a href>` links (multi-page, no
  router).
- **mermaid.js** via the same CDN (`mermaid@11`), `startOnLoad:false`,
  `securityLevel:"loose"`, dark `themeVariables`. Each page renders its own
  current-state diagram(s) with a small render script.
- Pages are self-contained HTML; only `style.css` and the mermaid CDN are shared
  dependencies. No build step (these are static docs opened directly / served).

## Method — build from inspection (per page)

For each content page (`ingestion`, `retrieval`, `chat`, plus the `index`
overview):

1. **Inspect** the real code for that layer (`src/...`, and for chat the
   `web/src/...` modal/pipeline data too). Read modes/stages/knobs from source,
   not from the old docs.
2. **Record** each non-trivial claim in `report.html` as
   `claim → file:line → verdict`. Verdict is `verified` (matches code),
   `drift` (old doc said otherwise; note the correction), or `removed`
   (old doc claimed something no longer in code).
3. **Write** the page using only verified facts. Diagrams reflect the verified
   current graph.

The old `index.html`'s §1–§17 are mined for *candidate* claims to verify, then
discarded — none of its prose is copied forward unverified.

## Cross-cutting updates

- **CLAUDE.md** "Where to look" row "Reference design graph" currently points to
  `docs/common ground/index.html`. Update it to
  `docs/common ground/Elements/index.html` (the real path) and note the new
  multi-page set.
- The CLAUDE.md interconnected-artifact table lists
  `docs/common ground/index.html` as the "Reference design graph". Keep that
  pointer accurate after the rebuild.

## Non-goals (YAGNI)

- No dated per-feature changelog sections in the HTML (lives in
  `docs/system/changelog.md`).
- No build tooling / bundler for the docs — static files only.
- The Demo handoff under `docs/upgrades/Demo/` is untouched.
- No new diagrams beyond what each layer needs to be understood at current state.

## Success criteria

- `docs/common ground/Elements/` contains exactly: `style.css`, `index.html`,
  `ingestion.html`, `retrieval.html`, `chat.html`, `report.html`. Old files gone.
- Every page opens in a browser, nav works, mermaid diagrams render (dark theme).
- Every non-trivial claim on a content page has a matching `report.html` row with
  a `file:line` anchor; spot-checking three rows per page confirms the anchor
  points at code that supports the claim.
- The chat page's deep-tutor stage graph matches the actual stage order/knobs in
  `src/services/chat/agents/deep_tutor.py` (+ `orchestrator_workers.py`,
  `coverage.py`) and `web/src/data/tutorPipeline.ts`.
- CLAUDE.md pointer updated.

## Verification

- Open each page on a local file:// or via the dev static server; confirm nav +
  mermaid render and dark theme.
- Browser-check (`:5175` not required — these are static docs) by opening the
  files directly in Chrome; confirm no console errors from mermaid.
- Cross-read `report.html` rows against the cited `file:line`.
