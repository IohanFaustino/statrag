# Elements docs restructure + Services deep-dive — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the `docs/common ground/Elements/` static doc set into a three-hub hierarchy (Ingestion / Features / Services), point the homepage at the hubs, and rebuild the Services pages from naive stubs into extensive, diagram-rich deep-dives.

**Architecture:** Static HTML + a shared `style.css` (dark theme) + per-page inline mermaid render + a hand-maintained `sidebar.js`. No build step, no app changes. Existing top-level `ingestion.html` / `retrieval.html` are already rich hand-written pages — their content migrates into the hubs. The naive generated `services/*.html` become hand-written rich pages; `services/_generate.py` is repointed to emit only the index.

**Tech Stack:** HTML5, CSS (existing `style.css`), Mermaid 11 (CDN), vanilla JS (`sidebar.js`). Verification via `grep`/`python3` assertions + a browser render check.

**Spec:** `docs/superpowers/specs/2026-06-08-elements-docs-restructure-design.md`

**Working dir for all paths below:** `docs/common ground/Elements/` (inside the repo root). Quote the path in shell — it contains a space.

---

## Conventions used by every page (reference — do not skip)

**Page shell.** Two shells exist; reuse the matching one.

- **Top-level page** (`home.html`, `index.html`, `report.html`): `<body data-base="">`, `href="style.css"`, `href="sidebar.js"`, mermaid CDN in `<head>`.
- **Subdir page** (`ingestion/`, `features/`, `services/`, `modes/`, `models/`): `<body data-base="../">`, `href="../style.css"`, `<script src="../sidebar.js">`, mermaid CDN in `<head>`.

**Subdir page skeleton** (copy verbatim, fill `TITLE` / `BODY`):

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>statrag — TITLE</title>
<link rel="stylesheet" href="../style.css" />
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
</head>
<body data-base="../">
<aside id="side" class="side"></aside>
<div class="content">
<header>
  <h1><span class="accent">TITLE</span> <span class="pill">PILL</span></h1>
  <div class="sub">SUBTITLE</div>
</header>
<main>
BODY
</main>
</div>
<script>
  mermaid.initialize({ startOnLoad:false, theme:"dark", securityLevel:"loose",
    themeVariables:{ primaryColor:"#1b1e22", primaryTextColor:"#e6e8eb",
      primaryBorderColor:"#E5484D", lineColor:"#9aa1aa", fontSize:"14px" } });
  (async () => {
    const blocks = [...document.querySelectorAll(".mermaid")];
    for (let i=0;i<blocks.length;i++){
      const src = blocks[i].dataset.src || blocks[i].textContent;
      try { const { svg } = await mermaid.render("m"+i, src); blocks[i].innerHTML = svg; }
      catch(e){ blocks[i].innerHTML = "<pre style='color:#d2a24c'>"+String(e)+"</pre>"; }
    }
  })();
</script>
<script src="../sidebar.js"></script>
</body>
</html>
```

**Mermaid blocks** use the double-encoded pattern from existing pages: a `data-src="..."` attribute with HTML-entity-escaped source (`&quot;` for `"`, `&gt;`/`&lt;`, `&#10;` for newline-in-label, `&#9656;`), AND the same source as visible text inside the div as a fallback. Copy the exact pattern from `retrieval.html:30-55`.

**Accuracy rule (from spec).** Before writing any "verified from code" claim, open the named source file and confirm line numbers / names / values. Code wins over older docs. Do not invent knobs, event names, or models.

**Reusable verification snippet** (the "test" for doc tasks). Define `check()` per task:

```bash
cd "docs/common ground/Elements"
# 1. file exists & non-trivial
test -s PAGE.html && echo "exists ok"
# 2. required sections present (edit the grep list per task)
for s in "EXPECTED HEADING 1" "EXPECTED HEADING 2"; do
  grep -qF "$s" PAGE.html && echo "section ok: $s" || echo "MISSING: $s"
done
# 3. mermaid blocks balanced (every <div class="mermaid" has data-src)
python3 - <<'PY'
import re,sys,glob
for f in sys.argv[1:]:
    html=open(f).read()
    opens=html.count('class="mermaid"')
    srcs=html.count('data-src=')
    print(f, "mermaid divs", opens, "data-src", srcs, "OK" if opens<=srcs else "UNBALANCED")
PY
# pass the page to the python check, e.g.: ... PY ... PAGE.html  (append filename)
```

---

### Task 1: Rebuild the sidebar nav

**Files:**
- Modify: `docs/common ground/Elements/sidebar.js`

The current `PAGES`/`TOGGLES` reference deleted-to-be top-level pages and lack the new hubs. Rebuild so nav is: flat links (Home, Overview, Verification) + three toggle groups (Ingestion, Features, Services) + the existing Models group. The toggle/active logic (lines 54-95) is correct and must be preserved — only the `PAGES` and `TOGGLES` data (lines 8-52) change. The path-detection block at lines 56-59 only special-cases `/modes/` and `/models/`; extend it to also detect `/ingestion/`, `/features/`, `/services/`.

- [ ] **Step 1: Write the failing check**

```bash
cd "docs/common ground/Elements"
for s in '"ingestion/index.html", "All ingestion"' '"features/index.html", "All features"' '"services/index.html", "All services"' 'path.includes("/services/")'; do
  grep -qF "$s" sidebar.js && echo "ok: $s" || echo "MISSING: $s"
done
grep -q 'ingestion.html", "Ingestion"' sidebar.js && echo "STALE top-level ingestion link still present" || echo "stale link gone ok"
```

- [ ] **Step 2: Run it — expect MISSING / STALE present**

Run the Step 1 block. Expected: all four `MISSING:`, and `STALE ... still present`.

- [ ] **Step 3: Replace the `PAGES` array (lines 8-16)**

```javascript
  const PAGES = [
    ["home.html", "Home"],
    ["index.html", "Overview"],
    ["report.html", "Verification"]
  ];
```

- [ ] **Step 4: Replace the `TOGGLES` array (lines 19-52) — add three hub groups before Models**

```javascript
  const TOGGLES = [
    {
      label: "Ingestion",
      index: ["ingestion/index.html", "All ingestion"],
      children: [
        ["ingestion/pipeline.html", "Pipeline"],
        ["ingestion/chunking.html", "Chunking & payload"],
        ["ingestion/preprocessors.html", "Preprocessors"]
      ]
    },
    {
      label: "Features",
      index: ["features/index.html", "All features"],
      children: [
        ["modes/tutor.html", "Tutor"],
        ["modes/qa.html", "Q&A"],
        ["modes/facilitate.html", "Facilitate"],
        ["modes/resume.html", "Resume"]
      ]
    },
    {
      label: "Services",
      index: ["services/index.html", "All services"],
      children: [
        ["services/core.html", "Core"],
        ["services/ingestion.html", "Ingestion (code)"],
        ["services/retrieval.html", "Retrieval"],
        ["services/chat.html", "Chat"],
        ["services/eval.html", "Eval"]
      ]
    },
    {
      label: "Models",
      index: ["models/index.html", "All models"],
      children: [
        ["models/gpt-4o.html", "GPT-4o"],
        ["models/gpt-4o-mini.html", "GPT-4o mini"],
        ["models/gpt-5.4-nano-2026-03-17.html", "GPT-5.4 nano"],
        ["models/gpt-5.4-2026-03-05.html", "GPT-5.4"],
        ["models/deepseek-chat.html", "DeepSeek Chat"],
        ["models/deepseek-reasoner.html", "DeepSeek Reasoner"],
        ["models/deepseek-v4-pro.html", "DeepSeek V4 Pro"],
        ["models/meta-llama-llama-4-scout-17b-16e-instruct.html", "Llama 4 Scout 17B"],
        ["models/llama-3.3-70b-versatile.html", "Llama 3.3 70B"],
        ["models/openai-gpt-oss-120b.html", "GPT-OSS 120B"],
        ["models/openai-gpt-oss-20b.html", "GPT-OSS 20B"],
        ["models/gemini-2.5-flash.html", "Gemini 2.5 Flash"],
        ["models/gemini-2.5-pro.html", "Gemini 2.5 Pro"],
        ["models/qwen-plus.html", "Qwen Plus"],
        ["models/qwen-max.html", "Qwen Max"],
        ["models/qwen-turbo.html", "Qwen Turbo"]
      ]
    }
  ];
```

- [ ] **Step 5: Extend path-detection (current lines 56-59) to cover the new subdirs**

```javascript
  const base = document.body.dataset.base || "";
  const path = location.pathname;
  let here;
  const SUBDIRS = ["modes", "models", "ingestion", "features", "services"];
  const seg = SUBDIRS.find(d => path.includes("/" + d + "/"));
  if (seg) here = seg + "/" + path.split("/").pop();
  else here = path.split("/").pop() || "index.html";
```

- [ ] **Step 6: Run the check — expect all ok**

Run the Step 1 block. Expected: four `ok:` lines + `stale link gone ok`.

- [ ] **Step 7: Commit**

```bash
git add "docs/common ground/Elements/sidebar.js"
git commit -m "docs(elements): sidebar — 3 hub toggle groups, drop stale top-level links"
```

---

### Task 2: Rework the homepage around the three hubs

**Files:**
- Modify: `docs/common ground/Elements/home.html`

Keep the hero (lines 41-49), the "How it fits together" bento+mermaid (52-72), the "Stack at a glance" strip (84-93). Change two things: (a) the architecture diagram caption (line 66) links to the three hubs; (b) replace the "Four chat modes" section (74-82) and "Browse the docs" links-grid (95-104) with a single **"Three layers"** hub-card section + a small secondary link row (Overview · Verification · Models).

- [ ] **Step 1: Write the failing check**

```bash
cd "docs/common ground/Elements"
for s in 'href="ingestion/index.html"' 'href="features/index.html"' 'href="services/index.html"' 'Three layers'; do
  grep -qF "$s" home.html && echo "ok: $s" || echo "MISSING: $s"
done
```

- [ ] **Step 2: Run it — expect MISSING for all**

- [ ] **Step 3: Replace the architecture caption (line 66)**

```html
        <p class="caption">Three layers turn a book into an answer — <a href="ingestion/index.html">Ingestion</a> embeds it, <a href="services/retrieval.html">Retrieval</a> finds it, <a href="features/index.html">Features</a> teach it.</p>
```

- [ ] **Step 4: Replace the "Four chat modes" + "Browse the docs" sections (lines 74-104) with the hub section**

```html
  <section>
    <h2>Three layers</h2>
    <div class="links-grid">
      <a class="card mode-card" href="ingestion/index.html">
        <h3>Ingestion</h3>
        <p class="sub">How an OCR'd book becomes embedded Qdrant points: regex → enrich → chunk → embed → upsert, plus per-field collections and preprocessors.</p>
        <span class="pill">book → DB</span>
      </a>
      <a class="card mode-card" href="features/index.html">
        <h3>Features</h3>
        <p class="sub">What users get: the four chat modes (Tutor · Q&amp;A · Facilitate · Resume) and the deep-tutor pipeline that powers them.</p>
        <span class="pill">user-facing</span>
      </a>
      <a class="card mode-card chapter" href="services/index.html">
        <h3>Services</h3>
        <p class="sub">How the code is built: the Chinese-wall layers (core · ingestion · retrieval · chat · eval) with diagrams, modules, schemas, and invariants.</p>
        <span class="pill">architecture</span>
      </a>
    </div>
  </section>

  <section>
    <h2>Also</h2>
    <div class="strip">
      <a class="chip" href="index.html">Overview</a>
      <a class="chip" href="report.html">Verification</a>
      <a class="chip" href="models/index.html">Models</a>
    </div>
  </section>
```

- [ ] **Step 5: Run the check — expect all ok; open in browser**

Run Step 1 block (all `ok:`). Then open `file://<repo>/docs/common ground/Elements/home.html` in a browser and confirm: hero renders, the end-to-end mermaid renders (no yellow error box), three hub cards show, hover lift works.

- [ ] **Step 6: Commit**

```bash
git add "docs/common ground/Elements/home.html"
git commit -m "docs(elements): homepage — 3-hub layout, architecture links to hubs"
```

---

### Task 3: Ingestion hub (migrate + split the rich ingestion page)

**Files:**
- Create: `docs/common ground/Elements/ingestion/index.html` (hub overview + pipeline diagram)
- Create: `docs/common ground/Elements/ingestion/pipeline.html` (the 6-stage pipeline + providers)
- Create: `docs/common ground/Elements/ingestion/chunking.html` (chunking rule + payload field tables)
- Create: `docs/common ground/Elements/ingestion/preprocessors.html` (preprocessor registry, 12 books)
- Source content: existing `docs/common ground/Elements/ingestion.html` (rich, already verified-from-code) + `src/ingestion/processed/*.py` for the preprocessor list.

Reuse the **subdir page skeleton**. Migrate the existing `ingestion.html` sections, fixing two things: `data-base="../"` and `href="../style.css"` / `../sidebar.js`. Split: `index.html` = intro + Pipeline diagram (from `ingestion.html:20-46`) + Per-field collections (48-68) + a card row linking to the 3 child pages. `pipeline.html` = the same pipeline diagram + Providers table (70-106) + Commands (108-137). `chunking.html` = Chunking & payload (139-191). `preprocessors.html` = a new table of the 12 `*_preproc.py` files (one row each: preprocessor, what book/format it fixes — read each file's module docstring for the one-line role).

- [ ] **Step 1: Write the failing check**

```bash
cd "docs/common ground/Elements"
for f in ingestion/index.html ingestion/pipeline.html ingestion/chunking.html ingestion/preprocessors.html; do
  test -s "$f" && echo "exists: $f" || echo "MISSING FILE: $f"
done
grep -qF 'kobo_preproc' ingestion/preprocessors.html && echo "preproc ok" || echo "MISSING preproc rows"
grep -qF 'TARGET_TOKENS = 8000' ingestion/chunking.html && echo "chunk ok" || echo "MISSING chunk detail"
```

- [ ] **Step 2: Run it — expect MISSING for all four files**

- [ ] **Step 3: Create `ingestion/index.html`**

Use the subdir skeleton. TITLE `Ingestion`, PILL `Task · book → DB`, SUBTITLE the lede from `ingestion.html`. BODY: an intro `<section>`, the Pipeline `<section>` copied from `ingestion.html:20-46` (mermaid block verbatim), the Per-field collections `<section>` from `ingestion.html:48-68`, then a `<section>` with a `links-grid` of three `a.card` linking to `pipeline.html`, `chunking.html`, `preprocessors.html`.

- [ ] **Step 4: Create `ingestion/pipeline.html`**

Subdir skeleton. TITLE `Ingestion · Pipeline`. BODY: the Pipeline diagram section (`ingestion.html:20-46`), Providers section (`ingestion.html:70-106`), Commands section (`ingestion.html:108-137`) — copied verbatim. Re-confirm each cited line ref (`pipeline.py:95` etc.) still matches current `src/ingestion/pipeline.py` before keeping the claim; fix any drift.

- [ ] **Step 5: Create `ingestion/chunking.html`**

Subdir skeleton. TITLE `Ingestion · Chunking & payload`. BODY: the Chunking & payload section verbatim from `ingestion.html:139-191` (both payload tables). Re-confirm `build_documents.py` line refs.

- [ ] **Step 6: Create `ingestion/preprocessors.html`**

Subdir skeleton. TITLE `Ingestion · Preprocessors`. BODY: an intro paragraph (preprocessors are one-time offline steps producing `*_fixed.md` before ingestion — see the note at `ingestion.html:45`) + a `<table>` with header `Preprocessor | Book / source format | Role`. One row per file in `src/ingestion/processed/`: `atwan, cerqueira, cunningham, goodfellow, kobo, mackay, morgan, murphy, pesaran, prado, spark_ts, stock_watson`. Read each file's top docstring for the role; if absent, state the book slug + "structure reconstruction" generically.

- [ ] **Step 7: Run the check — expect all ok; browser-render `ingestion/index.html`**

Run Step 1 block (all exist + ok). Open `ingestion/index.html`, confirm sidebar shows the Ingestion group expanded with the active page highlighted, and the pipeline mermaid renders.

- [ ] **Step 8: Commit**

```bash
git add "docs/common ground/Elements/ingestion/"
git commit -m "docs(elements): ingestion hub — index + pipeline/chunking/preprocessors pages"
```

---

### Task 4: Features hub

**Files:**
- Create: `docs/common ground/Elements/features/index.html`
- Source: `docs/common ground/Elements/modes/index.html` (mode blurbs), `modes/tutor.html` (deep-tutor pipeline summary), spec §"Features hub".

The hub frames user-facing capabilities and links to the existing `modes/` detail pages — it does NOT duplicate retrieval detail (one short blurb linking to `services/retrieval.html`).

- [ ] **Step 1: Write the failing check**

```bash
cd "docs/common ground/Elements"
test -s features/index.html && echo "exists" || echo "MISSING FILE"
for s in 'href="../modes/tutor.html"' 'href="../modes/qa.html"' 'href="../modes/facilitate.html"' 'href="../modes/resume.html"' 'href="../services/retrieval.html"'; do
  grep -qF "$s" features/index.html && echo "ok: $s" || echo "MISSING: $s"
done
```

- [ ] **Step 2: Run it — expect MISSING FILE + all MISSING**

- [ ] **Step 3: Create `features/index.html`**

Subdir skeleton. TITLE `Features`, PILL `user-facing`. BODY:
1. Intro `<section>`: what "features" means here (the capabilities a user invokes; each mode is a different teaching contract over the same hybrid retrieval).
2. `<section>` "Four chat modes" — a `modes-grid` of four `a.card.mode-card` (use `.chapter` variant for Facilitate + Resume, matching `home.html:77-81`) linking to `../modes/<mode>.html`. Pull the one-line blurbs from `modes/index.html`.
3. `<section>` "The deep-tutor pipeline" — a short prose summary (concept→query-plan → coverage loop → orchestrator-workers synthesis → figure-judge/vision → answer) + a card linking to `../modes/tutor.html` for the full diagram. Do NOT redraw the full pipeline here.
4. `<section>` "Powered by retrieval" — one paragraph: every mode runs on the hybrid dense+sparse retrieval stack; link to `../services/retrieval.html` for the deep-dive. No duplication.

- [ ] **Step 4: Run the check — expect all ok; browser-render**

Open `features/index.html`; confirm the Features sidebar group is expanded with modes as children; mode cards link correctly.

- [ ] **Step 5: Commit**

```bash
git add "docs/common ground/Elements/features/"
git commit -m "docs(elements): features hub — frames 4 modes + deep-tutor, links retrieval"
```

---

### Task 5: Repoint the services generator to index-only + rebuild the index page

**Files:**
- Modify: `docs/common ground/Elements/services/_generate.py`
- Modify (regenerate): `docs/common ground/Elements/services/index.html`

The 5 detail pages become hand-written rich pages (Tasks 6-10), so the generator must stop emitting them (or it would overwrite the rich pages). Keep the `SERVICES` metadata list (id/name/layer/path/blurb) — it still drives the index table. Remove `service_page()` and its use in `main()`; keep `index_page()`. Update the module docstring to say it now emits only `index.html`.

- [ ] **Step 1: Write the failing check**

```bash
cd "docs/common ground/Elements/services"
python3 - <<'PY'
src=open("_generate.py").read()
print("emits-detail" if "for s in SERVICES:" in src and "service_page" in src else "index-only ok")
PY
```

- [ ] **Step 2: Run it — expect `emits-detail`**

- [ ] **Step 3: Edit `_generate.py` — drop detail emission**

In `main()` replace the body with:

```python
def main() -> None:
    (HERE / "index.html").write_text(index_page())
    print("wrote services/index.html (detail pages are hand-maintained)")
```

Delete the `service_page()` function (lines 116-148). Update the docstring's "Emits:" line to: `Emits: index.html only. The 5 detail pages are hand-written rich pages (diagrams + deep-dive + schemas + invariants); this script must NOT overwrite them.`

- [ ] **Step 4: Add an "Ingestion (code)" disambiguation note to `index_page()`**

In the `index_page()` body, after the existing `<p class="caption">` (the "Source of truth…" line), add:

```python
    body = body.replace(
        '<p class="caption">Source of truth',
        '<p class="caption">Each layer page is a deep-dive: sequence + dataflow diagrams, per-module breakdown, schemas/contracts, and the invariants that govern it. Source of truth',
        1,
    )
```

(Place this transform inside `index_page()` before `return page_shell(...)`, operating on the assembled `body` string.)

- [ ] **Step 5: Regenerate + check**

```bash
cd "docs/common ground/Elements/services" && python3 _generate.py
python3 - <<'PY'
src=open("_generate.py").read()
print("index-only ok" if "service_page" not in src else "STILL emits detail")
PY
grep -qF 'deep-dive' index.html && echo "caption ok" || echo "MISSING caption update"
```

Expected: `wrote services/index.html …`, `index-only ok`, `caption ok`.

- [ ] **Step 6: Commit**

```bash
git add "docs/common ground/Elements/services/_generate.py" "docs/common ground/Elements/services/index.html"
git commit -m "docs(elements): services generator emits index only; detail pages hand-written"
```

---

### Task 6: Services · Core deep-dive

**Files:**
- Modify (rewrite): `docs/common ground/Elements/services/core.html`
- Source: `src/core/config.py`, `src/core/qdrant_store.py`, `src/core/__init__.py`, `docs/system/invariants.md`.

Rewrite the stub into a deep page with the four mandated section types. Read the two source modules first.

- [ ] **Step 1: Write the failing check**

```bash
cd "docs/common ground/Elements"
for s in "Sequence" "Per-module" "Schemas" "Rationale" "class=\"mermaid\""; do
  grep -qF "$s" services/core.html && echo "ok: $s" || echo "MISSING: $s"
done
```

- [ ] **Step 2: Run it — expect MISSING for all**

- [ ] **Step 3: Rewrite `services/core.html`** (subdir skeleton, TITLE `Core`, PILL `Core · shared infra`). Sections, in order:

1. **Spec** — keep the existing 4-row table (layer / path / import rule / "no CLU"), caption "verified from `src/core/__init__.py`".
2. **Dataflow** — a mermaid `flowchart` showing `config.py (Settings)` and `qdrant_store.py (client + collection helpers)` feeding both `ingestion/` and `services/*`. Caption: core is imported, never imports in-repo.
3. **Per-module deep-dive** — one `<h3>` + prose block per module:
   - `config.py` — the Pydantic `Settings`: env loading, the model-id fields (embedding model, reranker, default provider), ports, collection-name derivation. List the key settings fields you find (verify names/line nums).
   - `qdrant_store.py` — the client wrapper + `collection_names()` (cite `:43-48`), `ensure_text_collection` / `ensure_image_collection`, named vectors (dense 3072d + sparse), `IMAGE_VECTOR`. Note gotchas (auto-create on first ingest).
4. **Schemas & contracts** — a table of the Qdrant collection schema: text collection (named vectors `dense`=3072d cosine + sparse BM25; payload keys → link to ingestion/chunking.html) and image collection (dense-only on caption). Plus the config surface: a short table of the most-referenced settings env vars.
5. **Rationale & invariants** — why core imports nothing (the Chinese wall); link to `../index.html#` Chinese-wall section and `docs/system/invariants.md`. Note the relevant invariant numbers if present.

- [ ] **Step 4: Run the check — expect all ok; browser-render** (`services/core.html`: sidebar Services group active, mermaid renders).

- [ ] **Step 5: Commit**

```bash
git add "docs/common ground/Elements/services/core.html"
git commit -m "docs(elements): services/core deep-dive — dataflow, modules, schema, invariants"
```

---

### Task 7: Services · Ingestion (code-view) deep-dive

**Files:**
- Modify (rewrite): `docs/common ground/Elements/services/ingestion.html`
- Source: `src/ingestion/pipeline.py`, `build_documents.py`, `llm_enrich.py`, `llm_client.py`, `regex_pass.py`, `ingest_images_only.py`, `manifest.py`, `schema.py`, `__init__.py`.

This is the **code-architecture** view of the ingestion task (distinct from the `ingestion/` *hub*, which is the operator view). Cross-link the two: this page says "for the operator pipeline + commands, see the Ingestion hub". Focus on modules, the chunk-record schema, and import rules.

- [ ] **Step 1: Write the failing check**

```bash
cd "docs/common ground/Elements"
for s in "Per-module" "Schemas" "Rationale" "ingestion/index.html" "class=\"mermaid\""; do
  grep -qF "$s" services/ingestion.html && echo "ok: $s" || echo "MISSING: $s"
done
```

- [ ] **Step 2: Run it — expect MISSING for all**

- [ ] **Step 3: Rewrite `services/ingestion.html`** (subdir skeleton, TITLE `Ingestion (code)`, PILL `Task · external-input → DB`). Sections:

1. **Spec** — keep the existing 4-row table (path `src/ingestion/`, import rule "only `src.core`", entrypoint `python -m src.ingestion.pipeline`). Caption verified from `src/ingestion/__init__.py`.
2. **Call graph** — mermaid `flowchart`: `pipeline.run_chapter()` → `regex_pass` → `llm_enrich` (via `llm_client`) → `build_documents` → embed (OpenAI) + sparse (fastembed) → `qdrant_store` upsert → `manifest`. Label the image side branch (`ingest_images_only`).
3. **Per-module deep-dive** — `<h3>`+prose per module: `pipeline.py` (orchestrator, `run_chapter`, `--status`, `--force`, `--limit-sections`), `build_documents.py` (chunk rule + `_flat_meta`), `llm_enrich.py` + `llm_client.py` (DeepSeek-flash, thinking-disable), `regex_pass.py`, `ingest_images_only.py`, `manifest.py`, `schema.py` (the Pydantic models). Verify line refs.
4. **Schemas & contracts** — the chunk-record payload (link to `../ingestion/chunking.html` rather than re-table it) + `ImageMetadata` model from `schema.py` + manifest.json shape.
5. **Rationale & invariants** — why ingestion is a one-off "task" not a "service"; the import wall (reads `src.core` only; services read ingestion *artifacts* as files, never import it). Link invariants.
6. **Operator view** — a card linking to `../ingestion/index.html`.

- [ ] **Step 4: Run the check — expect all ok; browser-render**

- [ ] **Step 5: Commit**

```bash
git add "docs/common ground/Elements/services/ingestion.html"
git commit -m "docs(elements): services/ingestion code-view deep-dive"
```

---

### Task 8: Services · Retrieval deep-dive (migrate + extend)

**Files:**
- Modify (rewrite): `docs/common ground/Elements/services/retrieval.html`
- Source: existing top-level `docs/common ground/Elements/retrieval.html` (rich, verified) + `src/services/chat/retrieval.py`, `retrievers/density.py`, `diversity.py`, `image_density.py`, `rerankers.py`, `query_expansion.py`, `src/services/retrieval/{chain,retrievers,cli}.py`.

The top-level `retrieval.html` is already a rich deep-dive. Migrate its four sections into `services/retrieval.html` (fix paths to `../`), then add the two missing mandated section types: **schemas/contracts** and **rationale/invariants**.

- [ ] **Step 1: Write the failing check**

```bash
cd "docs/common ground/Elements"
for s in "Hybrid retrieval pipeline" "Components" "Image retrieval path" "Two retrieval entrypoints" "Schemas" "Rationale" 'href="../style.css"'; do
  grep -qF "$s" services/retrieval.html && echo "ok: $s" || echo "MISSING: $s"
done
```

- [ ] **Step 2: Run it — expect the migrated headings + Schemas/Rationale MISSING**

- [ ] **Step 3: Rewrite `services/retrieval.html`** (subdir skeleton, TITLE `Retrieval`, PILL `Service · DB → results`). BODY = the four sections from top-level `retrieval.html:17-187` copied verbatim (Hybrid retrieval pipeline + its mermaid, Components table, Image retrieval path, Two retrieval entrypoints) — these already carry verified line refs. **Adjust nothing in the mermaid.** Then append two new sections:

4. **Schemas & contracts** — the tuning knobs as a table: RRF `k=60`, `rerank_top_k_in=50` / `rerank_top_n_out=10` (`config.py:73-74`), reranker model `BAAI/bge-reranker-v2-m3` (`config.py:72`), `_DIVERSITY_MAX=6`, `_TOP_SECTIONS=4`, `_FINAL_TOP_N=8`, the `TUTOR_*` env overrides, and the `RetrievalFlags` surface (query-expansion strategies, `adjacent_sections`). Verify each value against the cited file.
5. **Rationale & invariants** — why two entrypoints exist (standalone LangChain CLI vs in-process deep-tutor retrievers), why density-before-rerank, why sibling chunks are appended at near-zero score (rerank is the gate). Link `docs/system/invariants.md` (adjacency-recall, author-diversity invariants if numbered).

- [ ] **Step 4: Run the check — all ok; browser-render** (confirm the 8-node retrieval flowchart renders).

- [ ] **Step 5: Commit**

```bash
git add "docs/common ground/Elements/services/retrieval.html"
git commit -m "docs(elements): services/retrieval deep-dive — migrate + schemas/invariants"
```

---

### Task 9: Services · Chat deep-dive (the deepest page)

**Files:**
- Modify (rewrite): `docs/common ground/Elements/services/chat.html`
- Source (read before writing): `src/services/chat/api.py`, `modes.py`, `router.py`, `orchestrator.py`, `agents/{deep_tutor,qa,chapter,orchestrator_workers,coverage,image_judge,formula_recovery,formula_gaps,formula_cache}.py`, `llm/{router,structured,base}.py` + the 6 provider clients, `retrievers/`, `tools/`, `vision.py`, `kg.py`, `mode_impls/`, `schemas/{_core,output}.py`, `prompts/`. Also `docs/services/chat-features/36-deep-tutor.md` for the canonical pipeline graph and the `TUTOR_*` env table.

This page carries the most surface. Organize by sub-package so it stays navigable. Read the modules; do not invent SSE event names or knobs — pull them from `api.py` and `schemas/_core.py`.

- [ ] **Step 1: Write the failing check**

```bash
cd "docs/common ground/Elements"
for s in "SSE" "agents/" "llm/" "Per-module" "Schemas" "Rationale" "sequenceDiagram" "Deep-tutor pipeline"; do
  grep -qF "$s" services/chat.html && echo "ok: $s" || echo "MISSING: $s"
done
python3 - <<'PY'
h=open("services/chat.html").read()
print("mermaid count", h.count('class="mermaid"'))
PY
```

- [ ] **Step 2: Run it — expect MISSING for the new sections; mermaid count 0**

- [ ] **Step 3: Rewrite `services/chat.html`** (subdir skeleton, TITLE `Chat`, PILL `Service · user-facing`). Sections:

1. **Spec** — keep the existing 4-row table (path, import rule, entrypoint `uvicorn src.services.chat.api:app`). Caption verified from `__init__.py`.
2. **Request → SSE sequence** — a mermaid `sequenceDiagram`: Browser → `api.py` (POST chat) → `router.py`/`modes.py` (mode dispatch) → agent runner (e.g. `deep_tutor`) → retrieval + LLM → SSE token/event stream → Browser. Caption lists the actual SSE event types read from `api.py` (verify names — e.g. token/source/figure/status/done; correct to whatever the code emits).
3. **Sub-packages map** — a mermaid `flowchart` grouping: `agents/`, `llm/`, `retrievers/`, `tools/`, `prompts/`, `schemas/`, plus `vision.py`, `kg.py`, `mode_impls/`. Show `api → modes → agents → (retrievers + llm + tools)`.
4. **Deep-tutor pipeline** — embed/restate the canonical stage graph (concept→query-planner → retrieval → density+rerank → diversity → coverage loop → orchestrator-workers → figure-judge/vision → synthesis). Source it from `docs/services/chat-features/36-deep-tutor.md`; link there. (Mirror the modal card per CLAUDE.md's lockstep note — but this is read-only doc, just keep it consistent.)
5. **Per-module deep-dive** — grouped `<h3>` per sub-package with a table of files + role + key entry inside each: `agents/` (deep_tutor, qa, chapter, orchestrator_workers, coverage, image_judge, formula_recovery/gaps/cache, ow_*), `llm/` (router, structured, base + 6 clients — note DeepSeek thinking-disable, qwen json_schema caveat, gemini non-strict JSON if reflected in code/comments), `retrievers/`, `tools/`, `vision.py`, `kg.py`, `mode_impls/`, `prompts/`.
6. **Schemas & contracts** — request knobs from `schemas/_core.py` (the `TUTOR_*` / retrieval flags surface), response models from `schemas/output.py`, and the SSE event contract table. Verify field names.
7. **Rationale & invariants** — the lockstep rule (a stage spans logic+prompt+schema+modal+docs+tests), why structured-output is enforced, link `docs/system/invariants.md` + `changelog.md` + `chat-features/` index.
8. **Related** — cards to `../features/index.html`, `../modes/index.html`, `../models/index.html`.

- [ ] **Step 4: Run the check — all ok; mermaid count ≥ 3; browser-render**

Open `services/chat.html`; confirm both the sequence diagram and the pipeline flowchart render without the yellow error box.

- [ ] **Step 5: Commit**

```bash
git add "docs/common ground/Elements/services/chat.html"
git commit -m "docs(elements): services/chat deep-dive — SSE seq, sub-packages, pipeline, schemas"
```

---

### Task 10: Services · Eval deep-dive

**Files:**
- Modify (rewrite): `docs/common ground/Elements/services/eval.html`
- Source: `src/services/eval/{dataset,generator,metrics,runner}.py`, `src/services/chat/eval/*` (the chat-side eval harnesses), `docs/eval/image_label_instructions.md`.

Smaller page, but still gets the four section types. Be honest about placeholder status (the `src/services/eval/` package is a placeholder; the *live* eval lives under `src/services/chat/eval/` + `pytest -m quality_images`).

- [ ] **Step 1: Write the failing check**

```bash
cd "docs/common ground/Elements"
for s in "Per-module" "Schemas" "Rationale" "placeholder" "quality_images"; do
  grep -qF "$s" services/eval.html && echo "ok: $s" || echo "MISSING: $s"
done
```

- [ ] **Step 2: Run it — expect MISSING for all**

- [ ] **Step 3: Rewrite `services/eval.html`** (subdir skeleton, TITLE `Eval`, PILL `Service · placeholder`). Sections:

1. **Spec** — table (path `src/services/eval/`, import rule only `src.core`, entry "placeholder — no stable CLI").
2. **Two eval surfaces** — mermaid `flowchart` / prose distinguishing the placeholder `src/services/eval/` package from the live chat-side harnesses in `src/services/chat/eval/` (facilitate_eval, ow_*_compare, planner_chain_compare, structured_synth_compare, ts_components_compare) + the `pytest -m quality_images` image-quality runner.
3. **Per-module deep-dive** — `src/services/eval/`: dataset.py / generator.py / metrics.py / runner.py (roles, marked placeholder). Then the chat-side eval modules table.
4. **Schemas & contracts** — eval dataset/metrics shape (read `metrics.py`); the image-label KPIs from `docs/eval/image_label_instructions.md`.
5. **Rationale & invariants** — why eval is split (generic placeholder vs feature-specific harnesses next to the code they test); link `../report.html` (Verification) + `docs/eval/image_label_instructions.md`.

- [ ] **Step 4: Run the check — all ok; browser-render**

- [ ] **Step 5: Commit**

```bash
git add "docs/common ground/Elements/services/eval.html"
git commit -m "docs(elements): services/eval deep-dive — placeholder + live harness split"
```

---

### Task 11: Delete migrated top-level pages, dead-link sweep, final render verify

**Files:**
- Delete: `docs/common ground/Elements/ingestion.html`, `retrieval.html`, `chat.html`
- Touch (only if dead links found): any page linking to the deleted files.

- [ ] **Step 1: Write the failing check — no inbound links to the deleted pages, and no broken hrefs**

```bash
cd "docs/common ground/Elements"
# (a) any remaining links to the to-be-deleted top-level pages? (exclude subdir paths like ingestion/ and services/ingestion.html)
grep -rEno 'href="(\.\./)?(ingestion|retrieval|chat)\.html"' . --include=*.html | grep -vE 'services/(ingestion|retrieval|chat)\.html' || echo "no stale top-level links"
# (b) dead-link sweep: every relative href resolves to a file
python3 - <<'PY'
import re,os,glob
bad=[]
for f in glob.glob("**/*.html",recursive=True):
    base=os.path.dirname(f)
    for m in re.findall(r'href="([^"#:]+\.html)(?:#[^"]*)?"', open(f).read()):
        tgt=os.path.normpath(os.path.join(base,m))
        if not os.path.exists(tgt): bad.append((f,m))
print("DEAD LINKS:",bad) if bad else print("no dead links")
PY
```

- [ ] **Step 2: Run it — expect stale links to the 3 top-level pages (they still exist + are still linked from nowhere-or-somewhere) until deleted**

Note: after Tasks 1-10 the sidebar + homepage no longer link the top-level trio; this step confirms nothing else does before deleting.

- [ ] **Step 3: Delete the three migrated top-level pages**

```bash
cd "docs/common ground/Elements"
git rm ingestion.html retrieval.html chat.html
```

- [ ] **Step 4: Run the dead-link sweep again — expect `no stale top-level links` and `no dead links`**

If the sweep reports a dead link, fix the offending href (it should point into a hub/subdir page) and re-run.

- [ ] **Step 5: Full render pass in the browser**

Open each of: `home.html`, `index.html`, `ingestion/index.html`, `features/index.html`, `services/index.html`, `services/core.html`, `services/ingestion.html`, `services/retrieval.html`, `services/chat.html`, `services/eval.html`. For each confirm: sidebar renders with the correct group expanded + active link highlighted, every mermaid block renders (no yellow `<pre>` error), no obvious layout break. Note any failures and fix before commit.

- [ ] **Step 6: Commit**

```bash
git add -A "docs/common ground/Elements"
git commit -m "docs(elements): remove migrated top-level ingestion/retrieval/chat pages"
```

---

## Self-review notes (author)

- **Spec coverage:** 3 hubs → T2 (home links), T3 (ingestion), T4 (features), T5-T10 (services). Fold/delete → T11. Services 4 content types → enforced by the per-task grep checks (Sequence/dataflow, Per-module, Schemas, Rationale) in T6-T10. Sidebar → T1. Keep modes/ → T4 links into it; no rename. Retrieval once → T8 (deep) + T4 (summary link). ✓
- **No app changes:** every path under `docs/common ground/Elements/`. ✓
- **Accuracy:** each services task names the exact source files to read before writing, per the spec accuracy rule. ✓
- **Verification:** doc-appropriate — grep section presence + mermaid balance + browser render, in a fail→write→pass→commit rhythm. ✓
