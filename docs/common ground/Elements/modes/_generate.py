#!/usr/bin/env python3
"""Generate the per-mode doc pages (detailed: purpose, diagram, model, schema).

Source of truth: src/services/chat/modes.py (ModeSpec registry), agents/qa.py +
agents/chapter.py + agents/deep_tutor.py (runners), schemas/output.py (output models),
cost.py / changelog (draft model). Static output only — a maintenance convenience,
not a build dependency. Re-run after the mode registry changes:

    cd "docs/common ground/Elements/modes" && python3 _generate.py

Emits: index.html + one <mode>.html per registered mode. Nav lives in ../sidebar.js
(hand-maintained toggle config) — this script does NOT touch it.
"""
from __future__ import annotations
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Each mode: a dict of verified facts. Sources cited inline on the page.
MODES = [
    {
        "id": "tutor", "name": "Tutor", "arch": "single-agent (tool loop)",
        "schema": "TutorAnswer / DeepTutorAnswer",
        "model": "nano for aux stages; <b>draft stage</b> overrides to <code>TUTOR_DRAFT_MODEL</code> (qwen-plus) with the full OpenAI model as fallback",
        "tools": "retrieve", "retrieval": "rerank gated (off until M4) at the mode level; the deep-tutor pipeline does its own rerank",
        "memory": "auto (carries conversation context)", "validators": "citation",
        "prompt": "prompts/tutor.py — TUTOR_INSTRUCTIONS", "src": "agents/deep_tutor.py + modes.py:153-167",
        "purpose": "The default, deepest mode. Answers a question with a multi-author, structured tutorial: TL;DR, definition, formal statement, worked example + intuition, applications, and further reading — with inline citations, figures, and rendered math.",
        "when": "Use for conceptual questions where you want depth, multiple textbook perspectives, formulas, and figures (\"What is the bias-variance tradeoff?\"). Not for a one-line fact (use Q&amp;A) or for walking a whole chapter (use Facilitate / Resume).",
        "diagram": """flowchart TD
  Q[\"Question\"] --> QP[\"Query planner (nano)<br/>concepts + queries + facets\"]
  QP --> RET[\"Multi-query retrieval -> RRF\"]
  RET --> DR[\"Density + author-diversity + rerank\"]
  DR --> CC{\"Coverage check (nano)\"}
  CC -. \"missing facet\" .-> RET
  CC --> FJ[\"Figure judge\"]
  FJ --> PL[\"Planner-orchestrator (LLM)\"]
  PL --> DFT[\"Draft / synthesis (draft model)\"]
  DFT --> VE[\"Vision explain\"]
  VE --> A[\"TutorAnswer\"]
  style PL fill:#3a1d1f,stroke:#E5484D,color:#fff
  style CC fill:#1f2a1a,stroke:#3fb950,color:#fff""",
        "diagram_cap": "Full pipeline on the Chat &amp; deep-tutor page. The draft node is the only stage that uses the heavy draft model; everything else is nano.",
        "fields": [
            ("tldr", "Intro: direct answer + roadmap of the sections."),
            ("definition", "Markdown paragraph defining the concept."),
            ("formal_statement", "Verbatim numbered theorem when sources state one; else empty (heading dropped)."),
            ("example_intuition", "Three cases analysed, then explicit intuition."),
            ("applications", "Corpus-grounded use-cases grouped by domain."),
            ("further_reading", "Related topics + open questions, with citations."),
            ("citations / math_blocks / figures", "Inline [n] sources, rendered math, figure refs."),
        ],
        "fields_note": "DeepTutorAnswer aspects (schemas/output.py:111-158); assembled into TutorAnswer.text + aspects for the UI.",
    },
    {
        "id": "qa", "name": "Q&amp;A", "arch": "multi-agent (4-node graph)",
        "schema": "QAAnswer",
        "model": "nano (all four nodes; per-stage override via stageModels)",
        "tools": "none (retrieval is a graph node, not a tool)", "retrieval": "rerank=True, rerank_top_n=4 (narrow, high-precision)",
        "memory": "off", "validators": "none (grounding is a runtime verify node)",
        "prompt": "prompts/qa.py — QA_GENERATE_PROMPT", "src": "agents/qa.py:3, modes.py:170-186",
        "purpose": "Punctual, scoped Q&amp;A. Extracts the precise gap the question asks about (and what it assumes you already know), retrieves a small high-precision set, generates a terse grounded answer, then verifies that every claim is supported.",
        "when": "Use for a specific, bounded question where you want a short, sourced answer fast — not a full tutorial. The verify node flags unsupported claims and reports a confidence.",
        "diagram": """flowchart LR
  Q[\"Question\"] --> SC[\"scope (nano)<br/>target_gap + assumed_known\"]
  SC --> RET[\"retrieve (top 4, rerank)\"]
  RET --> GEN[\"scoped generate\"]
  GEN --> VF[\"verify grounding\"]
  VF --> A[\"QAAnswer\"]
  style VF fill:#1f2a1a,stroke:#3fb950,color:#fff""",
        "diagram_cap": "Four nodes, run in order (agents/qa.py). One schema-repair retry on the generate node (ADR-005).",
        "fields": [
            ("text", "Terse markdown with inline [n] citation markers."),
            ("scope", "The resolved QAScope (target_gap, assumed_known, answer_form), echoed for transparency."),
            ("citations", "Sources matching the [n] markers."),
            ("math_blocks", "Rendered math, if any."),
            ("grounding", "Verify verdict: {ok, unsupported[], confidence}."),
        ],
        "fields_note": "schemas/output.py:237-251.",
    },
    {
        "id": "facilitate", "name": "Facilitate", "arch": "multi-agent (chapter pipeline)",
        "schema": "ChapterDigest",
        "model": "nano (per-stage override via CHAPTER_&lt;STAGE&gt;_MODEL)",
        "tools": "none", "retrieval": "rerank=False — structural fetch, NOT relevance search (embeddings only resolve fuzzy subtopic → heading)",
        "memory": "off", "validators": "none (optional ground node)",
        "prompt": "prompts/chapter.py — CHAPTER_MAP_FACILITATE_PROMPT", "src": "agents/chapter.py:3-4, modes.py:193-207",
        "purpose": "An ordered, didactic walkthrough of a whole chapter. Fetches the chapter's sections in the book's own order and teaches each one (verbose map, ~250-400 tokens/section), streaming each block as it finishes so you watch the chapter build top to bottom.",
        "when": "Use to learn a chapter section by section in its intended order. Structural, not search-driven — the chapter's section order IS the answer order. Pick Resume instead when you want a compressed recap.",
        "diagram": """flowchart TD
  Q[\"Chapter request\"] --> PS[\"parse-scope\"]
  PS --> FC[\"fetch-chapter (structural, in order)\"]
  FC --> RS[\"resolve-subtopics (fuzzy, nano)\"]
  RS --> MAP[\"map per-section IN ORDER<br/>facilitate = verbose ~250-400 tok\"]
  MAP --> ST[\"stitch\"]
  ST --> GR[\"ground\"]
  GR --> A[\"ChapterDigest (blocks in order)\"]
  style MAP fill:#3a1d1f,stroke:#E5484D,color:#fff""",
        "diagram_cap": "Same pipeline as Resume; only the map prompt + verbosity differ. Order fixed by section_id, never re-sorted by relevance.",
        "fields": [
            ("mode", "\"facilitate\" — tells the renderer which header/styling."),
            ("scope", "ChapterScope: book_slug, chapter_id, requested_subtopics, resolution."),
            ("intro / outro", "Framing before/after the blocks."),
            ("blocks[]", "ChapterBlock per section: h2_path, section_id, body, page_from, page_to — list position IS chapter order."),
            ("citations / math_blocks / grounding", "Sources, math, verify verdict."),
        ],
        "fields_note": "schemas/output.py:296-313. Chapter knobs below.",
        "chapter_knobs": True,
    },
    {
        "id": "resume", "name": "Resume", "arch": "multi-agent (chapter pipeline)",
        "schema": "ChapterDigest",
        "model": "nano (per-stage override via CHAPTER_&lt;STAGE&gt;_MODEL)",
        "tools": "none", "retrieval": "rerank=False — structural fetch, NOT relevance search",
        "memory": "off", "validators": "none (optional ground node)",
        "prompt": "prompts/chapter.py — CHAPTER_MAP_RESUME_PROMPT", "src": "agents/chapter.py:3-4, modes.py:209-223",
        "purpose": "An ordered, compressed recap of a whole chapter. Same structural pipeline as Facilitate, but the map step is terse (~60-100 tokens/section) — a faithful condensed summary in reading order.",
        "when": "Use to review or skim a chapter you have already studied, or to get the gist of one quickly. Pick Facilitate instead when you want a full teaching walkthrough.",
        "diagram": """flowchart TD
  Q[\"Chapter request\"] --> PS[\"parse-scope\"]
  PS --> FC[\"fetch-chapter (structural, in order)\"]
  FC --> RS[\"resolve-subtopics (fuzzy, nano)\"]
  RS --> MAP[\"map per-section IN ORDER<br/>resume = compact ~60-100 tok\"]
  MAP --> ST[\"stitch\"]
  ST --> GR[\"ground\"]
  GR --> A[\"ChapterDigest (blocks in order)\"]
  style MAP fill:#241a33,stroke:#9b6bd6,color:#fff""",
        "diagram_cap": "Identical pipeline to Facilitate; the map prompt is compact instead of verbose.",
        "fields": [
            ("mode", "\"resume\" — renderer styling."),
            ("scope", "ChapterScope: book_slug, chapter_id, requested_subtopics, resolution."),
            ("intro / outro", "Framing before/after the blocks."),
            ("blocks[]", "ChapterBlock per section: h2_path, section_id, body, page_from, page_to — list position IS chapter order."),
            ("citations / math_blocks / grounding", "Sources, math, verify verdict."),
        ],
        "fields_note": "schemas/output.py:296-313. Chapter knobs below.",
        "chapter_knobs": True,
    },
]

CHAPTER_KNOBS = [
    ("CHAPTER_RESOLVE", "1", "LLM-resolve requested subtopics that did not match a heading by string."),
    ("CHAPTER_MAX_SECTIONS", "30", "Cap on sections mapped per chapter."),
    ("CHAPTER_STITCH", "1", "Run the stitch pass that links per-section digests into a flowing whole."),
    ("CHAPTER_GROUND", "1", "Run the grounding pass that checks the digest against the fetched sections."),
]

MERMAID = """<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>"""
RENDER = """<script>
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
</script>"""


def page_shell(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>statrag — {title}</title>
<link rel="stylesheet" href="../style.css" />
{MERMAID}
</head>
<body data-base="../">
<aside id="side" class="side"></aside>
<div class="content">
{body}
</div>
<script src="../sidebar.js"></script>
{RENDER}
</body>
</html>
"""


def mode_page(m: dict) -> str:
    fields = "\n      ".join(
        f'<tr><td><code>{f}</code></td><td>{d}</td></tr>' for f, d in m["fields"]
    )
    knobs = ""
    if m.get("chapter_knobs"):
        rows = "\n      ".join(
            f'<tr><td><code>{k}</code></td><td>{d}</td><td>{desc}</td></tr>'
            for k, d, desc in CHAPTER_KNOBS
        )
        knobs = f"""
  <section>
    <h2>Chapter knobs</h2>
    <table>
      <tr><th>Env var</th><th>Default</th><th>Effect</th></tr>
      {rows}
    </table>
    <p class="caption">Source: <code>src/services/chat/agents/chapter.py:45-48</code>.</p>
  </section>"""
    # mermaid src goes in BOTH data-src and text content (render reads data-src first).
    diagram = m["diagram"].replace('"', "&quot;")
    body = f"""<header>
  <h1><span class="accent">{m['name']}</span> mode <span class="pill">{m['arch']}</span></h1>
  <div class="sub">{m['purpose']}</div>
</header>
<main>
  <section>
    <h2>What it serves</h2>
    <div class="card"><p style="margin:0">{m['when']}</p></div>
  </section>
  <section>
    <h2>Pipeline</h2>
    <div class="diagram-wrap"><div class="mermaid" data-src="{diagram}">{m['diagram']}</div></div>
    <p class="caption">{m['diagram_cap']}</p>
  </section>
  <section>
    <h2>Spec</h2>
    <table>
      <tr><th>Mode id</th><td><code>{m['id']}</code></td></tr>
      <tr><th>Architecture</th><td>{m['arch']}</td></tr>
      <tr><th>Default model</th><td>{m['model']}</td></tr>
      <tr><th>Output schema</th><td><code>{m['schema']}</code></td></tr>
      <tr><th>Tools</th><td>{m['tools']}</td></tr>
      <tr><th>Retrieval</th><td>{m['retrieval']}</td></tr>
      <tr><th>Memory</th><td>{m['memory']}</td></tr>
      <tr><th>Post-validators</th><td>{m['validators']}</td></tr>
      <tr><th>System prompt</th><td><code>{m['prompt']}</code></td></tr>
    </table>
    <p class="caption">Source: <code>src/services/chat/{m['src']}</code>.</p>
  </section>
  <section>
    <h2>Output fields</h2>
    <table>
      <tr><th>Field</th><th>Meaning</th></tr>
      {fields}
    </table>
    <p class="caption">{m['fields_note']}</p>
  </section>{knobs}
</main>"""
    return page_shell(m["name"].replace("&amp;", "&"), body)


def index_page() -> str:
    rows = []
    for m in MODES:
        rows.append(
            f'<tr><td><a href="{m["id"]}.html">{m["name"]}</a></td>'
            f'<td>{m["arch"]}</td><td><code>{m["schema"]}</code></td>'
            f'<td>{m["purpose"]}</td></tr>'
        )
    table = "\n      ".join(rows)
    body = f"""<header>
  <h1>statrag — <span class="accent">Modes</span></h1>
  <div class="sub">The chat modes you can pick. Each is a registered ModeSpec with its own runner, diagram, default model, and output schema. <span class="pill">4 modes</span></div>
</header>
<main>
  <section>
    <h2>All modes</h2>
    <table>
      <tr><th>Mode</th><th>Architecture</th><th>Output schema</th><th>What it serves</th></tr>
      {table}
    </table>
    <p class="caption">Source of truth: <code>src/services/chat/modes.py</code> (register_all_modes). Click a mode for its diagram, spec, and output fields.</p>
  </section>
  <section>
    <h2>Two families</h2>
    <div class="card"><p style="margin:0"><b>Search modes</b> (Tutor, Q&amp;A) retrieve by relevance to a question. <b>Chapter modes</b> (Facilitate, Resume) do a <b>structural fetch</b> of a whole chapter and emit a <code>ChapterDigest</code> in the book's own section order — not a search.</p></div>
  </section>
</main>"""
    return page_shell("Modes", body)


def main() -> None:
    (HERE / "index.html").write_text(index_page())
    n = 0
    for m in MODES:
        (HERE / f"{m['id']}.html").write_text(mode_page(m))
        n += 1
    print(f"wrote modes/index.html + {n} mode pages")


if __name__ == "__main__":
    main()
