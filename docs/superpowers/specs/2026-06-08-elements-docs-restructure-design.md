# Elements docs restructure + Services deep-dive — design

**Date:** 2026-06-08
**Scope:** `docs/common ground/Elements/` static HTML doc set
**Goal:** Introduce three intermediate hub layers (Ingestion / Features / Services), point the homepage at them via the system-architecture diagram, and rebuild the Services pages from naive stubs into an extensive, diagram-rich deep-dive.

## Motivation

The Elements doc set currently mixes a landing page, a flat "Overview", a handful of rich top-level ops pages (`ingestion.html`, `retrieval.html`, `chat.html`), and three generated subdirs (`services/`, `modes/`, `models/`). There is no clear middle layer: the homepage links straight to leaf pages, and the `services/` pages are thin (a spec table + one-line module list) despite the chat service being the largest, most intricate part of the system. We want a clean three-hub hierarchy and a Services section that actually documents the code.

## Decisions (locked with user)

1. **Features = what, Services = how.** Features hub covers user-facing capabilities (the 4 chat modes + deep-tutor pipeline + a retrieval *summary*). Services hub covers the code architecture layers (core, ingestion-as-code, retrieval, chat, eval).
2. **Fold** the top-level ops pages into the hubs — single hierarchy, no parallel page sets.
3. **Services depth = all four content types:** sequence/dataflow diagrams, per-module deep-dive, schemas/contracts, design rationale + invariants.
4. **Keep `modes/` dir**; add `features/index.html` as the hub that frames the modes. No dir rename (avoids dead links + generator churn).
5. **Retrieval documented once** — full deep-dive in `services/retrieval.html`; Features hub gives a short "retrieval powers every mode" summary that links there. No duplication.

## Target hierarchy

```
Home          home.html      hero + 3-layer architecture diagram + 3 hub cards
Overview      index.html     keep: what-it-is, stack, Chinese wall
Verification  report.html    keep standalone (cross-cutting concern)
Models        models/        keep: reference set, linked from services/chat + features

ingestion/    HUB    index + per-stage detail        ← absorbs top-level ingestion.html
features/     HUB    index framing modes/ + deep-tutor
services/     HUB    index + 5 deep layer pages       ← rebuilt from stubs
```

**Deleted after content migration:** top-level `ingestion.html`, `retrieval.html`, `chat.html`.
- `ingestion.html` → `ingestion/` hub.
- `retrieval.html` → `services/retrieval.html` deep-dive.
- `chat.html` splits: feature/mode content → `features/`, code/architecture content → `services/chat.html`.

## Component design

### Homepage (`home.html`)
- Keep the hero, the end-to-end mermaid flow, and the stack strip.
- Replace the 5-card "Browse the docs" grid with **3 primary hub cards**: Ingestion / Features / Services, each with a one-line "what's inside".
- The "How it fits together" architecture diagram stays the visual anchor; its caption links to the three hubs (book → ingestion → Qdrant → retrieval → features). Overview / Verification / Models demoted to a small secondary link row.

### Ingestion hub (`ingestion/index.html` + stage pages)
- Pipeline overview diagram: preprocess → enrich → chunk → embed → upsert.
- Per-stage cards/sections describing each step.
- The three user gates (G1 metadata, G2 preview, G3 full) from the `rag-add-book` flow.
- Preprocessor registry table (the 12 `*_preproc.py` under `src/ingestion/processed/`).
- Outputs: `data/parsed/manifest.json`, per-field `field_textbooks` / `field_images` collections.
- Source modules: `pipeline.py`, `build_documents.py`, `llm_enrich.py`, `regex_pass.py`, `ingest_images_only.py`, `manifest.py`, `schema.py`.

### Features hub (`features/index.html`)
- Frames user-facing capabilities. Cards for the 4 modes link to existing `modes/` detail pages.
- Deep-tutor pipeline summary (query plan → coverage → orchestrator-workers → vision/figure-judge → synthesis), linking to `modes/tutor.html` for the full diagram.
- Short "retrieval powers every mode" blurb → links to `services/retrieval.html`. No retrieval detail duplicated here.

### Services hub (`services/`)
Index keeps the 5-layer table + Chinese-wall callout. Each layer page (`core`, `ingestion`, `retrieval`, `chat`, `eval`) is rebuilt to include, beyond the existing spec table + module list:

- **Diagrams** — a request→response (or data-path) sequence diagram, plus a module call-graph / dataflow mermaid.
- **Per-module deep-dive** — responsibility, inputs/outputs, key functions, gotchas. Replaces the one-line role table.
- **Schemas & contracts** — per layer:
  - *chat*: SSE event contract (`api.py`), request knobs (`schemas/_core.py`, `TUTOR_*` env), response models (`schemas/output.py`).
  - *core*: Qdrant collection schema + config surface (`config.py`, `qdrant_store.py`).
  - *retrieval*: RRF + rerank params, dense/sparse retriever contract (`chain.py`, `retrievers.py`).
  - *ingestion*: chunk record schema (`schema.py`), manifest shape.
  - *eval*: dataset/metrics shape (placeholder, marked as such).
- **Rationale + invariants** — why-this-way notes; cross-links to `docs/system/invariants.md` and `docs/system/changelog.md`.

Chat is the deepest page — it must cover `agents/` (deep_tutor, qa, chapter, orchestrator_workers, coverage, formula_recovery/gaps/cache, image_judge, ow_*), `llm/` (6 provider clients + `router.py` + `structured.py`), `retrievers/` (density, diversity, image_density), `tools/`, `vision.py`, `kg.py`, `mode_impls/`, `schemas/`, `prompts/`.

### Sidebar (`sidebar.js`)
- Flat links: Home · Overview · Verification.
- Three toggle groups: **Ingestion** (hub + stage pages), **Features** (hub + 4 modes as children), **Services** (hub + 5 layers as children).
- Models toggle stays as-is.
- Remove the deleted top-level `ingestion.html` / `retrieval.html` / `chat.html` entries.

### Generators
- Keep the `_generate.py` convention where structure repeats: `services/_generate.py` extended to emit the four richer sections from structured per-service data; `modes/` and `models/` generators untouched.
- Ingestion and Features hubs are bespoke enough to hand-write (no generator).

## Accuracy rule

Every "verified from code" claim must be read from the actual modules before writing — matching the existing "current-state · verified from code" ethos. No invented behaviour, knobs, or event names. When code and an older doc disagree, code wins and the doc note is updated.

## Out of scope

- No changes to the live app (`web/`, `src/`). Docs only.
- No new design language / CSS overhaul — reuse `style.css`, the mermaid dark theme, JetBrains Mono.
- Models reference pages unchanged.
- Verification (`report.html`) content unchanged (only its sidebar position).

## Success criteria

- Home links to exactly three hubs via cards + architecture diagram.
- Each hub index loads, renders its diagrams, and links to its children with no dead links.
- Top-level `ingestion.html` / `retrieval.html` / `chat.html` removed; their content present in the hubs.
- Each `services/<layer>.html` has: ≥1 sequence/dataflow diagram, per-module deep-dive, a schemas/contracts section, and a rationale/invariants section.
- Sidebar reflects the new structure on every page; active-state highlighting works.
- All mermaid diagrams render (no parse errors).
