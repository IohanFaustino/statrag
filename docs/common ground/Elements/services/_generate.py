#!/usr/bin/env python3
"""Generate the per-service doc pages + index.

Source of truth: the repo architecture (Chinese wall in each __init__.py) —
src/core/, src/ingestion/, src/services/{retrieval,chat,eval}/. Static html only;
a maintenance convenience, not a build dependency. Re-run after the layer layout
changes:

    cd "docs/common ground/Elements/services" && python3 _generate.py

Emits: index.html + <id>.html per service (5). Nav lives in ../sidebar.js
(hand-maintained) — this script does NOT touch it.
"""
from __future__ import annotations
from pathlib import Path

HERE = Path(__file__).resolve().parent

# fields: id, name, accent, layer, path, imports, blurb, modules[(file, role)],
#         entry, related[(href, label)]
SERVICES = [
    {
        "id": "core", "name": "Core", "accent": "#9aa1aa",
        "layer": "Core · shared infra", "path": "src/core/",
        "imports": "Nothing in the repo — only third-party libs. ingestion/ and services/ may import core; core never imports them.",
        "blurb": "The shared system layer: configuration and the Qdrant client/store wrapper. Everything else depends on core; core depends on nothing in-repo.",
        "modules": [
            ("config.py", "Pydantic settings — env, model ids, ports, collection naming."),
            ("qdrant_store.py", "Qdrant client + per-field collection helpers (textbooks/images)."),
        ],
        "entry": "Imported as <code>src.core.config</code> / <code>src.core.qdrant_store</code> — no CLI.",
        "related": [("../index.html", "Overview — Chinese wall")],
    },
    {
        "id": "ingestion", "name": "Ingestion", "accent": "#d2a24c",
        "layer": "Task · external-input → DB", "path": "src/ingestion/",
        "imports": "Only <code>src.core</code> + third-party. No imports from services/. Other tasks/services never import ingestion.",
        "blurb": "One-off pipeline that turns an OCR'd book into enriched, embedded Qdrant points. Reads per-book YAML + preprocessor output, writes the field_textbooks / field_images collections.",
        "modules": [
            ("pipeline.py", "Orchestrates preprocess → enrich → embed → upsert (CLI entry)."),
            ("build_documents.py", "Section chunking (1 section = 1 chunk, 8000-tok split)."),
            ("llm_enrich.py", "LLM enrichment (DeepSeek-flash default)."),
            ("regex_pass.py", "Deterministic regex cleanup pass."),
            ("ingest_images_only.py", "Image-only ingest path for figures."),
            ("manifest.py", "Writes data/parsed/manifest.json."),
        ],
        "entry": "<code>python -m src.ingestion.pipeline --book &lt;slug&gt; --chapter chNN</code> (pipeline.py:271 main).",
        "related": [("../ingestion.html", "Ingestion ops page")],
    },
    {
        "id": "retrieval", "name": "Retrieval", "accent": "#3fb950",
        "layer": "Service · DB → results", "path": "src/services/retrieval/",
        "imports": "Only <code>src.core</code>. Never imports other services or ingestion.",
        "blurb": "Hybrid query service: dense + sparse BM25 over the per-field collections, fused with Reciprocal Rank Fusion, optional cross-encoder rerank. The retrieval primitive every chat mode builds on.",
        "modules": [
            ("chain.py", "Hybrid query chain — embed, dense+sparse search, RRF, rerank."),
            ("retrievers.py", "Dense / sparse retriever wrappers over Qdrant."),
            ("cli.py", "Stand-alone retrieval CLI."),
        ],
        "entry": "<code>python -m src.services.retrieval.cli \"&lt;question&gt;\" --book &lt;slug&gt;</code>.",
        "related": [("../retrieval.html", "Retrieval ops page")],
    },
    {
        "id": "chat", "name": "Chat", "accent": "#E5484D",
        "layer": "Service · user-facing", "path": "src/services/chat/",
        "imports": "Only <code>src.core</code>. Reads manifest.json + book YAML as files, never imports ingestion.",
        "blurb": "The SSE-streaming conversational layer: a FastAPI app exposing the four chat modes over hybrid retrieval, including the deep-tutor pipeline (query planning → coverage → orchestrator-workers → vision).",
        "modules": [
            ("api.py", "FastAPI app + SSE endpoints (app = FastAPI, uvicorn entry)."),
            ("modes.py", "ModeSpec registry — tutor / qa / facilitate / resume."),
            ("agents/", "Runners: deep_tutor, qa, chapter, orchestrator_workers, coverage, …"),
            ("prompts/", "Per-stage system prompts."),
            ("schemas/", "Request knobs + output models."),
            ("llm/router.py", "Provider / model routing (see Models)."),
        ],
        "entry": "<code>uvicorn src.services.chat.api:app</code> (dev: ./scripts/dev.sh → :8766).",
        "related": [("../chat.html", "Chat & deep-tutor page"), ("../modes/index.html", "Modes"), ("../models/index.html", "Models")],
    },
    {
        "id": "eval", "name": "Eval", "accent": "#615CED",
        "layer": "Service · placeholder", "path": "src/services/eval/",
        "imports": "Only <code>src.core</code>. Never imports other services or ingestion.",
        "blurb": "Evaluation scaffolding — dataset building, generation, and metrics for retrieval / answer quality. Present but a placeholder; not wired into the live app.",
        "modules": [
            ("dataset.py", "Eval dataset construction."),
            ("generator.py", "Candidate / answer generation for scoring."),
            ("metrics.py", "Scoring metrics."),
            ("runner.py", "Eval run driver."),
        ],
        "entry": "Placeholder — no stable CLI yet.",
        "related": [("../report.html", "Verification page")],
    },
]


def page_shell(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>statrag — {title}</title>
<link rel="stylesheet" href="../style.css" />
</head>
<body data-base="../">
<aside id="side" class="side"></aside>
<div class="content">
{body}
</div>
<script src="../sidebar.js"></script>
</body>
</html>
"""


def service_page(s: dict) -> str:
    mods = "\n      ".join(
        f'<tr><td><code>{f}</code></td><td>{r}</td></tr>' for f, r in s["modules"]
    )
    rel = " · ".join(f'<a href="{h}">{l}</a>' for h, l in s["related"])
    body = f"""<header>
  <h1><span class="accent">{s['name']}</span> <span class="pill">{s['layer']}</span></h1>
  <div class="sub">{s['blurb']}</div>
</header>
<main>
  <section>
    <h2>Spec</h2>
    <table>
      <tr><th>Layer</th><td>{s['layer']}</td></tr>
      <tr><th>Path</th><td><code>{s['path']}</code></td></tr>
      <tr><th>Import rule</th><td>{s['imports']}</td></tr>
      <tr><th>Entrypoint</th><td>{s['entry']}</td></tr>
    </table>
    <p class="caption">Chinese-wall rule verified from <code>{s['path']}__init__.py</code>.</p>
  </section>
  <section>
    <h2>Key modules</h2>
    <table>
      <tr><th>Module</th><th>Role</th></tr>
      {mods}
    </table>
  </section>
  <section>
    <h2>Related</h2>
    <div class="card"><p style="margin:0">{rel}</p></div>
  </section>
</main>"""
    return page_shell(s["name"], body)


def index_page() -> str:
    rows = "\n      ".join(
        f'<tr><td><a href="{s["id"]}.html">{s["name"]}</a></td>'
        f'<td>{s["layer"]}</td><td><code>{s["path"]}</code></td>'
        f'<td>{s["blurb"]}</td></tr>'
        for s in SERVICES
    )
    body = f"""<header>
  <h1>statrag — <span class="accent">Services</span></h1>
  <div class="sub">The architecture layers behind statrag — each a package with one responsibility and a strict import rule. <span class="pill">{len(SERVICES)} layers · Chinese wall</span></div>
</header>
<main>
  <section>
    <h2>All services</h2>
    <table>
      <tr><th>Service</th><th>Layer</th><th>Path</th><th>What it does</th></tr>
      {rows}
    </table>
    <p class="caption">Source of truth: each package <code>__init__.py</code> (import rules) + module listings. Click a service for its modules + entrypoint.</p>
  </section>
  <section>
    <h2>The Chinese wall</h2>
    <div class="card"><p style="margin:0"><b>Core</b> imports nothing in-repo. <b>Tasks</b> (ingestion) and <b>Services</b> (retrieval, chat, eval) import only core — never each other, never ingestion. Encoded in every <code>__init__.py</code>.</p></div>
  </section>
</main>"""
    return page_shell("Services", body)


def main() -> None:
    (HERE / "index.html").write_text(index_page())
    for s in SERVICES:
        (HERE / f"{s['id']}.html").write_text(service_page(s))
    print(f"wrote services/index.html + {len(SERVICES)} service pages")


if __name__ == "__main__":
    main()
