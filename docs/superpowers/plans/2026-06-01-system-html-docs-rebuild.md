# System HTML Docs Rebuild — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `docs/common ground/Elements/` with a clean, multi-page, current-state HTML documentation set built by inspecting the actual code.

**Architecture:** Five static HTML pages (`index`, `ingestion`, `retrieval`, `chat`, `report`) sharing one `style.css` (dark theme) and a top nav. Each content page is written from direct code inspection; every non-trivial claim is logged in `report.html` as `claim → file:line → verdict`. No build step; mermaid.js via CDN renders diagrams.

**Tech Stack:** Static HTML5, one shared CSS file, mermaid@11 (CDN). No bundler, no framework. Verification = open in browser + grep checks (no pytest — these are docs).

---

## Important notes for every task

- **Inspect, don't trust.** The old `docs/common ground/Elements/index.html` (§1–§17) and the markdown docs (`docs/system/`, `docs/services/`, `docs/tasks/`) are HINTS. Verify each claim against the actual source before writing it. Read the real `src/...` / `web/src/...` files.
- **Chinese wall** (from `CLAUDE.md`): `src/core` imports nothing in-repo; `src/ingestion` (task) imports only `src.core`; each `src/services/<name>` imports only `src.core`, never another service or a task. State this accurately on the relevant pages.
- **report.html is append-only across tasks.** Each content task adds its verification rows. Do NOT rewrite earlier rows.
- **Verification step for a page** = (a) grep the file for required structural markers, (b) open it in Chrome and confirm nav works + mermaid renders + no console error. The agent records the browser result in the commit message.
- **Commit after each task.** End commit messages with the Co-Authored-By trailer:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  ```

---

## File Structure

Created under `docs/common ground/Elements/`:

| File | Responsibility |
|---|---|
| `style.css` | Shared dark theme (CSS custom props + card/table/verdict/pill/nav classes). Single source of styling. |
| `index.html` | Landing/overview: stack, 3-layer Chinese wall, one cross-cutting flow diagram, nav. |
| `ingestion.html` | Ingestion task pipeline + collections + providers. |
| `retrieval.html` | Retrieval service: hybrid + RRF + density + rerank + diversity + image path. |
| `chat.html` | Chat service + deep-tutor pipeline DAG + modes + SSE/runs + providers + knobs. |
| `report.html` | Verification matrix (claim → file:line → verdict), built across tasks. |

Modified:
- `CLAUDE.md` — fix "Reference design graph" pointer.

Deleted:
- Old `docs/common ground/Elements/index.html`, `docs/common ground/Elements/report.html`.

---

## Task 0: Scaffold — remove old files, shared CSS, page skeletons

**Files:**
- Delete: `docs/common ground/Elements/index.html`, `docs/common ground/Elements/report.html`
- Create: `docs/common ground/Elements/style.css`
- Create (skeletons): `docs/common ground/Elements/index.html`, `ingestion.html`, `retrieval.html`, `chat.html`, `report.html`

- [ ] **Step 1: Remove the old files**

```bash
cd "/home/iohan/Documents/toolbox/AI_models/RAG/docs/common ground/Elements"
git rm index.html report.html
```

- [ ] **Step 2: Create the shared `style.css`**

Write `docs/common ground/Elements/style.css` with EXACTLY this content (extracted from the old theme + nav additions):

```css
:root{
  --bg:#0b0c0e; --panel:#141619; --panel2:#1b1e22; --line:#2a2e34;
  --txt:#e6e8eb; --dim:#9aa1aa; --accent:#E5484D; --ok:#3fb950; --warn:#d2a24c;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
  font:15px/1.6 ui-sans-serif,system-ui,"IBM Plex Sans",Segoe UI,Roboto,sans-serif}
header{padding:28px 32px 8px;border-bottom:1px solid var(--line)}
h1{margin:0 0 4px;font-size:22px;letter-spacing:.2px}
h1 .accent{color:var(--accent)}
.sub{color:var(--dim);font-size:13px}
nav.top{display:flex;gap:6px;flex-wrap:wrap;padding:12px 32px;border-bottom:1px solid var(--line);background:var(--panel)}
nav.top a{color:var(--dim);text-decoration:none;padding:6px 12px;border-radius:999px;border:1px solid var(--line);font-size:13px}
nav.top a:hover{color:var(--txt)}
nav.top a.active{background:var(--accent);border-color:var(--accent);color:#fff}
main{max-width:1080px;margin:0 auto;padding:24px 32px 64px}
section{margin:28px 0}
h2{font-size:16px;border-left:3px solid var(--accent);padding-left:10px;margin:0 0 12px}
h3{font-size:14px;color:var(--txt);margin:18px 0 8px}
p{color:#cdd2d8}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px}
.quote{background:var(--panel2);border-left:3px solid var(--dim);padding:12px 16px;border-radius:6px;color:#cdd2d8;font-style:italic}
.diagram-wrap{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:22px;min-height:300px;display:flex;align-items:center;justify-content:center;overflow:auto}
.caption{color:var(--dim);font-size:13px;margin-top:8px;text-align:center}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{border:1px solid var(--line);padding:9px 12px;text-align:left;vertical-align:top}
th{background:var(--panel2);color:var(--dim);font-weight:600}
.yes{color:var(--ok);font-weight:600}
.warn{color:var(--warn);font-weight:600}
.no{color:var(--accent);font-weight:600}
code{background:#000;border:1px solid var(--line);border-radius:4px;padding:1px 5px;font-size:13px}
.verdict{border:1px solid var(--warn);background:rgba(210,162,76,.08);border-radius:10px;padding:16px 18px}
.verdict.v-ok{border-color:var(--ok);background:rgba(63,185,80,.08)}
.verdict b{color:var(--warn)}
.verdict.v-ok b{color:var(--ok)}
ul{color:#cdd2d8}
a{color:var(--accent)}
.pill{display:inline-block;font-size:11px;padding:2px 8px;border-radius:999px;border:1px solid var(--line);color:var(--dim);margin-left:6px}
```

- [ ] **Step 3: Create the shared page skeleton for all 5 pages**

Each page uses this exact template. Replace `PAGETITLE`, mark the matching nav link `class="active"`, and leave a `<main>` body placeholder. The mermaid CDN + init script is included on every page (harmless if a page has no diagram).

Template (use for `index.html` with `<a href="index.html" class="active">`; for the others move `class="active"` to the matching link):

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>statrag — PAGETITLE</title>
<link rel="stylesheet" href="style.css" />
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
</head>
<body>
<header>
  <h1>statrag — <span class="accent">PAGETITLE</span></h1>
  <div class="sub">Local-first RAG over OCR'd statistics textbooks. <span class="pill">current-state · verified from code</span></div>
</header>
<nav class="top">
  <a href="index.html">Overview</a>
  <a href="ingestion.html">Ingestion</a>
  <a href="retrieval.html">Retrieval</a>
  <a href="chat.html">Chat &amp; deep-tutor</a>
  <a href="report.html">Verification</a>
</nav>
<main>
  <!-- PAGE BODY -->
</main>
<script>
  mermaid.initialize({ startOnLoad:false, theme:"dark", securityLevel:"loose",
    themeVariables:{ primaryColor:"#1b1e22", primaryTextColor:"#e6e8eb",
      primaryBorderColor:"#E5484D", lineColor:"#9aa1aa", fontSize:"14px" } });
  // Render every .mermaid block on the page.
  (async () => {
    const blocks = [...document.querySelectorAll(".mermaid")];
    for (let i=0;i<blocks.length;i++){
      const src = blocks[i].dataset.src || blocks[i].textContent;
      try { const { svg } = await mermaid.render("m"+i, src); blocks[i].innerHTML = svg; }
      catch(e){ blocks[i].innerHTML = "<pre style='color:#d2a24c'>"+String(e)+"</pre>"; }
    }
  })();
</script>
</body>
</html>
```

For the 5 files set `class="active"` on: index→Overview, ingestion→Ingestion, retrieval→Retrieval, chat→Chat & deep-tutor, report→Verification. Set PAGETITLE to: `Overview`, `Ingestion`, `Retrieval`, `Chat & deep-tutor`, `Verification`.

For `report.html` body placeholder, seed the table shell:

```html
<section>
  <h2>Verification matrix</h2>
  <p>Every non-trivial claim on the content pages, traced to its source with a verdict. Built during the 2026-06-01 rebuild by inspecting the code, not the prior docs.</p>
  <table id="matrix">
    <tr><th>Page</th><th>Claim</th><th>Source (file:line)</th><th>Verdict</th></tr>
    <!-- ROWS APPENDED PER TASK -->
  </table>
  <p class="caption">Verdict legend: <span class="yes">verified</span> = matches code · <span class="warn">drift</span> = prior doc was wrong, corrected here · <span class="no">removed</span> = prior doc claimed something no longer in code.</p>
</section>
```

- [ ] **Step 4: Verify skeletons render**

```bash
cd "/home/iohan/Documents/toolbox/AI_models/RAG/docs/common ground/Elements"
ls   # expect: chat.html index.html ingestion.html report.html retrieval.html style.css
grep -l 'class="stylesheet"\|style.css' *.html | wc -l   # expect 5
grep -L 'nav class="top"' *.html   # expect: (empty — all have nav)
```

Then open `index.html` in Chrome (use the claude-in-chrome tools: load `file://<abs path>/index.html`), confirm: dark theme applied, nav bar shows 5 links, Overview link is highlighted, no console errors.

- [ ] **Step 5: Commit**

```bash
cd "/home/iohan/Documents/toolbox/AI_models/RAG"
git add "docs/common ground/Elements"
git commit -m "docs(html): scaffold multi-page system docs (shared css + skeletons)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 1: index.html — Overview page

**Inspect first (read these, verify claims):**
- `CLAUDE.md` (stack, top-level layout, Chinese-wall table) — but VERIFY against code.
- `src/core/__init__.py`, `src/ingestion/__init__.py`, `src/services/chat/__init__.py` — confirm the wall (what each imports).
- `src/core/config.py` — embedding model, LLM model defaults, Qdrant settings.
- `docs/system/architecture.md` — hint only.
- `ops/docker/docker-compose.yml` — Qdrant version, ports.

**Files:**
- Modify: `docs/common ground/Elements/index.html` (fill `<main>`)
- Modify: `docs/common ground/Elements/report.html` (append rows)

- [ ] **Step 1: Inspect and collect verified facts**

Read the files above. For each fact you will put on the page (stack versions, model IDs, default ports, the three wall rules), note the exact `file:line` that proves it. Example facts to capture: Qdrant version + dashboard port (from compose), embedding model `text-embedding-3-large` + dim (from `config.py`), default chat model (from `config.py`), the three import rules (from the three `__init__.py`).

- [ ] **Step 2: Write the Overview body**

Fill `<main>` with these sections (use real verified values, not the examples):
1. `<section>` "What it is" — one card: local-first hybrid RAG over OCR'd textbooks; dense+sparse per-field Qdrant collections + image collections.
2. `<section>` "Stack" — a `<table>`: Vector DB (Qdrant `<ver>`, port 6333), Embeddings, Chat LLMs, Ingestion-enrich LLM, Sparse, Chunking, Language. Values from `config.py` / compose / `CLAUDE.md` verified.
3. `<section>` "Three-layer Chinese wall" — a `<table>`: Core / Tasks / Services with the verified import rule for each, plus a one-line "encoded in each `__init__.py`".
4. `<section>` "End-to-end flow" — a `.diagram-wrap` containing `<div class="mermaid" data-src="...">`. Diagram (verify each node exists):

```
flowchart LR
  B["Book (OCR md)"] --> ING["Ingestion task<br/>preprocess → enrich → embed"]
  ING --> QD["Qdrant<br/>&lt;field&gt;_textbooks + _images"]
  QD --> RET["Retrieval service<br/>hybrid + RRF + rerank"]
  RET --> CHAT["Chat service<br/>modes + deep-tutor"]
  CHAT --> ANS["Answer (SSE stream)"]
```
   Add a `.caption` and links (relative `<a href>`) to the three layer pages.

- [ ] **Step 3: Append verification rows to report.html**

In `report.html` `#matrix`, append one `<tr>` per non-trivial claim on this page, e.g.:

```html
<tr><td>Overview</td><td>Embeddings = text-embedding-3-large (3072d)</td><td><code>src/core/config.py:NN</code></td><td class="yes">verified</td></tr>
```
   Add a row for: embedding model+dim, Qdrant version, dashboard port, default chat model, each of the 3 wall rules, sparse=bm25. Use the real line numbers captured in Step 1.

- [ ] **Step 4: Verify**

```bash
cd "/home/iohan/Documents/toolbox/AI_models/RAG/docs/common ground/Elements"
grep -c '<section>' index.html         # expect >=4
grep -c 'class="mermaid"' index.html   # expect >=1
grep -c '<tr>' report.html             # expect grew vs Task 0
```
   Open `index.html` in Chrome: the flow diagram renders, tables show real values, layer links navigate. Confirm no console errors.

- [ ] **Step 5: Commit**

```bash
cd "/home/iohan/Documents/toolbox/AI_models/RAG"
git add "docs/common ground/Elements/index.html" "docs/common ground/Elements/report.html"
git commit -m "docs(html): overview page from code inspection + verification rows

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: ingestion.html — Ingestion pipeline page

**Inspect first:**
- `src/ingestion/pipeline.py` — stage order, CLI flags (`--book`, `--chapter`, `--force`, `--status`, `--provider`).
- `src/ingestion/processed/*_preproc.py` — preprocess role (one example, e.g. `kobo_preproc.py`).
- `src/ingestion/regex_pass.py` — what it normalizes.
- `src/ingestion/llm_enrich.py` + `src/ingestion/llm_client.py` — enrichment LLM + provider default (DeepSeek v4-flash) vs OpenAI captioning.
- `src/ingestion/build_documents.py` — chunking (1 section = 1 chunk, 8000-token split, tiktoken cl100k_base), field→collection naming.
- `src/ingestion/schema.py`, `src/ingestion/manifest.py` — point/payload shape, manifest.
- `src/ingestion/ingest_images_only.py` — image-only path.
- `docs/tasks/ingestion.md` — hint only.
- A book yaml: `src/ingestion/books/*.yaml` — the `field`/`theme` keys.

**Files:**
- Modify: `docs/common ground/Elements/ingestion.html`
- Modify: `docs/common ground/Elements/report.html`

- [ ] **Step 1: Inspect and capture file:line for each stage + the chunking rule + the field→collection rule + the enrichment provider default.**

- [ ] **Step 2: Write the body sections:**
1. "Pipeline" — `.diagram-wrap` mermaid (verify each stage exists in `pipeline.py`):

```
flowchart TD
  SRC["Source md (per book/chapter)"] --> PRE["Preprocess<br/>processed/&lt;book&gt;_preproc.py"]
  PRE --> RGX["Regex pass<br/>normalize structure"]
  RGX --> ENR["LLM enrich<br/>DeepSeek v4-flash (default)"]
  ENR --> BLD["build_documents<br/>1 section = 1 chunk, split @8000 tok"]
  BLD --> EMB["Embed<br/>text-embedding-3-large (OpenAI)"]
  BLD --> CAP["Image caption (OpenAI vision)"]
  EMB --> UP["Qdrant upsert<br/>&lt;field&gt;_textbooks"]
  CAP --> UPI["Qdrant upsert<br/>&lt;field&gt;_images"]
```
2. "Per-field collections" — table: `<field>_textbooks` + `<field>_images`, `field` from book yaml, auto-created on first ingest.
3. "Providers" — table: enrich=DeepSeek v4-flash (non-thinking, cheap), embeddings=OpenAI, captioning=OpenAI vision; `--provider` flag.
4. "Commands" — the verified CLI: ingest / status / image-only.
5. "Chunking + payload" — chunk rule + key payload fields (from `schema.py`).

- [ ] **Step 3: Append report.html rows** for: stage order, chunk-split token count + tokenizer, field→collection naming, enrich provider default, image-only path existence. With real `file:line`.

- [ ] **Step 4: Verify** (same pattern as Task 1: grep sections/mermaid, open in Chrome, diagram renders).

- [ ] **Step 5: Commit**

```bash
git add "docs/common ground/Elements/ingestion.html" "docs/common ground/Elements/report.html"
git commit -m "docs(html): ingestion page from code inspection + verification rows

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: retrieval.html — Retrieval service page

**Inspect first:**
- `src/services/retrieval/` (the retrieval service package — read its modules; if the live hybrid query is the CLI: `src/services/retrieval/cli.py` and the chain/query module).
- ALSO the chat-side retrieval used by deep-tutor for accuracy: `src/services/chat/retrieval.py`, `src/services/chat/retrievers/density.py`, `retrievers/diversity.py`, `retrievers/image_density.py`, `src/services/chat/rerankers.py`, `src/services/chat/query_expansion.py`.
- `docs/services/retrieval.md` + `docs/services/chat-features/02-retrieval-rrf.md`, `04-reranker.md`, `42-author-diversity.md`, `46-adjacency-recall.md` — hints only.

**Note:** distinguish the standalone `src/services/retrieval` CLI from the chat service's in-process retrieval. State on the page which is which (both exist; the deep-tutor uses the chat-side retrievers). Verify by reading imports.

**Files:** modify `retrieval.html`, `report.html`.

- [ ] **Step 1: Inspect.** Capture: dense+sparse(bm25) fusion = RRF (where), density-select logic, cross-encoder reranker model + `top_n`, author-diversity mechanism (section budget, caps), adjacency expansion (sibling prefilter + rerank-as-gate), image-density path. Note `file:line` each.

- [ ] **Step 2: Write body:**
1. "Hybrid retrieval" mermaid:

```
flowchart TD
  Q["Query"] --> D["Dense<br/>text-embedding-3-large"]
  Q --> S["Sparse<br/>bm25 (fastembed)"]
  D --> RRF["RRF fusion"]
  S --> RRF
  RRF --> DEN["Density select"]
  DEN --> ADJ["Adjacent-section expansion<br/>(sibling, rerank-gated)"]
  ADJ --> RR["Cross-encoder rerank (top_n)"]
  RR --> DIV["Author diversity"]
  DIV --> OUT["Selected sources"]
```
2. "Components" table: each stage → file → what it does (verified).
3. "Images" — image-density retrieval path (`retrievers/image_density.py`), separate `<field>_images` collections.
4. "Two retrieval entrypoints" — note the standalone retrieval CLI vs chat in-process retrievers; which the tutor uses.

- [ ] **Step 3: Append report.html rows** (fusion=RRF, reranker model, diversity caps, adjacency gate, image path). Real `file:line`.

- [ ] **Step 4: Verify** (grep + Chrome render).

- [ ] **Step 5: Commit**

```bash
git add "docs/common ground/Elements/retrieval.html" "docs/common ground/Elements/report.html"
git commit -m "docs(html): retrieval page from code inspection + verification rows

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: chat.html — Chat service + deep-tutor pipeline page

This is the biggest page. The deep-tutor stage graph MUST match the actual code.

**Inspect first (authoritative — read fully):**
- `src/services/chat/modes.py` + `src/services/chat/mode_impls/` — the registered modes (tutor/qa/chapter/facilitate/resume). Confirm exact mode ids.
- `src/services/chat/agents/deep_tutor.py` — the stage order + every `TUTOR_*` env knob (grep `TUTOR_`).
- `src/services/chat/agents/orchestrator_workers.py`, `agents/coverage.py`, `agents/image_judge.py` — orchestrator/workers, coverage check, figure judge.
- `src/services/chat/agents/qa.py`, `agents/chapter.py` — other modes.
- `src/services/chat/api.py` + `src/services/chat/runs.py` — SSE endpoints, detached resumable runs, `seq`.
- `src/services/chat/llm/router.py` + `llm/*_client.py` — providers (OpenAI, DeepSeek, Groq, Gemini, Qwen) + routing. Confirm which are chat-only.
- `src/services/chat/schemas/_core.py` (request knobs) + `schemas/output.py` (DeepTutorAnswer / ChapterDigest fields).
- `web/src/data/tutorPipeline.ts` — the modal card nodes/edges (the graph users see). Cross-check it matches the backend.
- Hints: `docs/services/chat.md`, `docs/services/chat-features/36-deep-tutor.md`, `43`–`52`.

- [ ] **Step 1: Inspect.** Capture the exact ordered stage list from `deep_tutor.py`, the drafting-workflow options (single / organize / orchestrator), the full `TUTOR_*` knob list (`grep -rn "TUTOR_" src/services/chat/`), the mode ids from `modes.py`, the provider set from `router.py`, the SSE routes from `api.py`. Note `file:line` for each.

- [ ] **Step 2: Write body sections:**
1. "Modes" table — each mode id → runner → output schema → one-line purpose (verified from `modes.py`).
2. "Deep-tutor pipeline" — `.diagram-wrap` mermaid reflecting the VERIFIED stage order. Start from this shape but CORRECT it to match code:

```
flowchart TD
  Q["Question"] --> QP["Query planner (nano)<br/>concepts + queries[] + facets[]"]
  QP --> MQ["Multi-query retrieval ×N → RRF"]
  MQ --> DR["Density select + rerank<br/>+ adjacency"]
  DR --> AD["Author diversity"]
  AD --> CC{"Coverage check (nano)<br/>facets supported?"}
  CC -. "missing → neighbors then re-query (cap 1)" .-> MQ
  CC -->|ok| FJ["Figure judge (caption-first)"]
  FJ --> PL["Planner-Orchestrator (LLM)<br/>thesis + contrasts + tasks"]
  PL --> WF{"Drafting workflow"}
  WF -->|single| DFT["Single draft"]
  WF -->|organize| ORG["Long-context organizer"]
  WF -->|orchestrator| WK["Workers ‖ → Synthesizer"]
  DFT --> VE["Vision explain"]
  ORG --> VE
  WK --> VE
  VE --> ANS["Answer (SSE)"]
  style PL fill:#3a1d1f,stroke:#E5484D,color:#fff
  style CC fill:#1f2a1a,stroke:#3fb950,color:#fff
```
   If the code differs (a stage added/removed/renamed), change the diagram to match the code and log the difference as `drift` in report.html.
3. "Stages" table — each node → file → purpose (verified).
4. "Knobs" table — every `TUTOR_*` env var → default → effect (from grep).
5. "Providers" table — OpenAI / DeepSeek / Groq / Gemini / Qwen, chat-only vs also-ingest, router membership note for Groq `openai/gpt-oss-*` ids.
6. "Streaming (SSE + resumable runs)" — `POST /api/chat`, `GET /api/chat/{id}/stream?after=`, `GET /api/chat/{id}/status`; monotonic `seq`; ≤1 active run/conv; detached run persists with zero subscribers (from `runs.py` + `api.py`).
7. "Output schemas" — DeepTutorAnswer aspect fields + ChapterDigest blocks (from `schemas/output.py`).

- [ ] **Step 3: Append report.html rows** — at minimum: mode id list, deep-tutor stage order, drafting-workflow options, each SSE route, provider set, ≤1-active-run invariant, the DeepTutorAnswer field list. Real `file:line`. Mark any old-doc divergence `drift`.

- [ ] **Step 4: Verify** — grep sections + mermaid; open `chat.html` in Chrome; the pipeline diagram renders and matches `web/src/data/tutorPipeline.ts` node set. Note in commit that the graph was cross-checked against the modal data.

- [ ] **Step 5: Commit**

```bash
git add "docs/common ground/Elements/chat.html" "docs/common ground/Elements/report.html"
git commit -m "docs(html): chat + deep-tutor page from code inspection + verification rows

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Finalize — report headline, CLAUDE.md pointer, full browser pass

**Files:**
- Modify: `docs/common ground/Elements/report.html` (add headline summary)
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add a headline to report.html** above the matrix:

```html
<section>
  <h2>Headline</h2>
  <div class="verdict v-ok"><b>Rebuilt 2026-06-01 from code inspection.</b> The prior single-page index.html (§1–§17, a dated change-log) was replaced by four current-state pages + this audit. Every claim below was traced to a source file; drift rows mark where the old docs were wrong.</div>
</section>
```
   Then add a one-line count: total rows, # verified, # drift, # removed.

- [ ] **Step 2: Update CLAUDE.md pointer**

In `CLAUDE.md`, the "Where to look" table and the interconnected-artifact table both reference `docs/common ground/index.html` as "Reference design graph". Update to `docs/common ground/Elements/index.html` and adjust the description to "multi-page current-state system docs (Overview / Ingestion / Retrieval / Chat / Verification)".

```bash
cd "/home/iohan/Documents/toolbox/AI_models/RAG"
grep -n "common ground/index.html" CLAUDE.md   # find the references
```
   Edit each hit to the new path + description.

- [ ] **Step 3: Full browser pass**

Open all 5 pages in Chrome in sequence (via claude-in-chrome `file://` navigation). For each: nav highlights the right tab, all `.mermaid` diagrams render to SVG (no yellow error `<pre>`), tables show real values, no console errors. Fix any render failure (usually a mermaid syntax slip in `data-src`).

- [ ] **Step 4: Final structural check**

```bash
cd "/home/iohan/Documents/toolbox/AI_models/RAG/docs/common ground/Elements"
ls   # exactly: chat.html index.html ingestion.html report.html retrieval.html style.css
for f in *.html; do echo "$f:"; grep -c 'nav class="top"' "$f"; done   # each 1
grep -c '<tr>' report.html   # the full claim count
```

- [ ] **Step 5: Commit**

```bash
cd "/home/iohan/Documents/toolbox/AI_models/RAG"
git add "docs/common ground/Elements/report.html" CLAUDE.md
git commit -m "docs(html): finalize verification report + repoint CLAUDE.md reference graph

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review (done by plan author)

- **Spec coverage:** 5 pages (Tasks 0–4 create all 5; Task 5 finalizes) ✓; shared style.css (Task 0) ✓; top nav (Task 0 template) ✓; mermaid CDN dark (Task 0 template) ✓; per-page inspect→verify→write method (each content task Steps 1–3) ✓; report.html matrix with file:line verdicts (every content task Step 3 + Task 5 headline) ✓; CLAUDE.md pointer (Task 5) ✓; old files removed (Task 0) ✓; Demo untouched (not referenced) ✓; no changelog narrative (not added) ✓.
- **Placeholders:** diagram `data-src` blocks are explicitly "verify/correct against code" — intentional, since the agent must confirm node existence; not a placeholder for prose.
- **Consistency:** file paths, nav link set, and report.html row format identical across tasks; render script is the shared template's `.mermaid` loop used by every page.
