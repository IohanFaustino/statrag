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
        "tools_spec": "retrieve", "retrieval": "rerank gated (off until M4) at the mode level; the deep-tutor pipeline does its own rerank",
        "memory": "auto (carries conversation context)", "validators": "citation",
        "prompt": "prompts/tutor.py — TUTOR_INSTRUCTIONS", "src": "agents/deep_tutor.py + modes.py:153-167",
        "purpose": "The default, deepest mode. Answers a question with a multi-author, structured tutorial: TL;DR, definition, formal statement, worked example + intuition, applications, and further reading — with inline citations, figures, and rendered math.",
        "when": "Use for conceptual questions where you want depth, multiple textbook perspectives, formulas, and figures (\"What is the bias-variance tradeoff?\"). Not for a one-line fact (use Q&amp;A) or for walking a whole chapter (use Facilitate / Resume).",
        "agentic": """flowchart TD
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
        "agentic_cap": "Full pipeline on the Chat &amp; deep-tutor page. The draft node is the only stage that uses the heavy draft model; everything else is nano.",
        "funcgraph": """flowchart TD
  E[\"run_deep_tutor()\"] --> P[\"extract_concepts_chain()<br/>_planner_decompose/expand/consolidate\"]
  P -. \"EXTRACT_CONCEPTS / PLANNER_* prompts\" .- PR1[(\"prompts/deep_tutor.py\")]
  P --> R[\"_multi_query_candidates() / _wide_candidates()\"]
  R --> M[\"_rrf_merge()\"]
  M --> DV[\"_apply_section_parent_diversity()\"]
  DV --> DS[\"_density_select()\"]
  DS --> CV[\"coverage.py (COVERAGE_PROMPT)\"]
  CV -. \"missing facet\" .-> R
  CV --> FJ[\"image_judge.py (figure judge)\"]
  FJ --> SP[\"build_synthesis_plan() (SYNTHESIS_PLAN_PROMPT)\"]
  SP --> OW[\"orchestrator_workers.run_orchestrator_workers()<br/>run_author_worker() x authors -> _schema_fill()\"]
  OW -. \"ORCHESTRATOR / AUTHOR_WORKER / CRITIQUE / SCHEMA_FILL\" .- PR2[(\"prompts/deep_tutor.py\")]
  OW --> FR[\"formula_recovery.py\"]
  FR --> VE[\"vision.py (vision-explain)\"]
  VE --> A[\"DeepTutorAnswer\"]
  style OW fill:#3a1d1f,stroke:#E5484D,color:#fff
  style CV fill:#1f2a1a,stroke:#3fb950,color:#fff
  style PR1 fill:#241a33,stroke:#9b6bd6,color:#fff
  style PR2 fill:#241a33,stroke:#9b6bd6,color:#fff""",
        "prompts": [
            ("EXTRACT_CONCEPTS_PROMPT", "prompts/deep_tutor.py:18", "Concept extraction from the question."),
            ("PLANNER_DECOMPOSE_PROMPT / _EXPAND_ / _CONSOLIDATE_", "prompts/deep_tutor.py:835/878/915", "Query-plan chain: decompose, expand, consolidate."),
            ("COVERAGE_PROMPT", "prompts/deep_tutor.py:624", "Coverage check — is every facet covered?"),
            ("SYNTHESIS_PLAN_PROMPT", "prompts/deep_tutor.py:478", "Plan the answer before drafting."),
            ("ORCHESTRATOR_PROMPT / AUTHOR_WORKER_PROMPT / CRITIQUE_PROMPT", "prompts/deep_tutor.py:536/656/743", "Orchestrator-workers synthesis + self-critique."),
            ("SCHEMA_FILL_PROMPT", "prompts/deep_tutor.py:903", "Coerce free text into DeepTutorAnswer aspects."),
            ("DEEP_TUTOR_INSTRUCTIONS", "prompts/deep_tutor.py:133", "Persona + hard rules for the synthesizer."),
        ],
        "tools": [
            ("extract_concepts_chain → planner LLM", "nano LLM", "Builds the multi-author query plan."),
            ("_multi_query_candidates / _wide_candidates", "Qdrant field_textbooks (dense+BM25)", "Retrieve candidate sections per query."),
            ("_rrf_merge → _density_select → rerank", "cross-encoder reranker", "Fuse, diversify by author/section, rerank."),
            ("image_judge", "Qdrant field_images + vision LLM", "Pick + judge figures."),
            ("run_orchestrator_workers", "draft model (TUTOR_DRAFT_MODEL)", "Per-author synthesis workers + organizer."),
            ("vision-explain", "vision LLM", "Explain chosen figures in context."),
        ],
        "sources": [
            ("entrypoint", "agents/deep_tutor.py:2439 (run_deep_tutor)"),
            ("query plan", "agents/deep_tutor.py:1336/1309/1316/1325"),
            ("retrieval + fusion", "agents/deep_tutor.py:1353/1394/1366/1410/1452"),
            ("coverage", "agents/coverage.py"),
            ("figure judge", "agents/image_judge.py"),
            ("synthesis", "agents/orchestrator_workers.py:165 (+ ow_deepagents.py)"),
            ("formula recovery", "agents/formula_recovery.py"),
            ("vision", "vision.py"),
        ],
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
        "tools_spec": "none (retrieval is a graph node, not a tool)", "retrieval": "rerank=True, rerank_top_n=4 (narrow, high-precision)",
        "memory": "off", "validators": "none (grounding is a runtime verify node)",
        "prompt": "prompts/qa.py — QA_GENERATE_PROMPT", "src": "agents/qa.py:3, modes.py:170-186",
        "purpose": "Punctual, scoped Q&amp;A. Extracts the precise gap the question asks about (and what it assumes you already know), retrieves a small high-precision set, generates a terse grounded answer, then verifies that every claim is supported.",
        "when": "Use for a specific, bounded question where you want a short, sourced answer fast — not a full tutorial. The verify node flags unsupported claims and reports a confidence.",
        "agentic": """flowchart LR
  Q[\"Question\"] --> SC[\"scope (nano)<br/>target_gap + assumed_known\"]
  SC --> RET[\"retrieve (top 4, rerank)\"]
  RET --> GEN[\"scoped generate\"]
  GEN --> VF[\"verify grounding\"]
  VF --> A[\"QAAnswer\"]
  style VF fill:#1f2a1a,stroke:#3fb950,color:#fff""",
        "agentic_cap": "Four nodes, run in order (agents/qa.py). One schema-repair retry on the generate node (ADR-005).",
        "funcgraph": """flowchart TD
  E[\"run_qa()\"] --> SC[\"extract_scope()\"]
  SC -. \"QA_SCOPE_PROMPT\" .- P1[(\"prompts/qa.py\")]
  SC --> RT[\"retrieve_for_gap()<br/>hybrid, top 4, rerank\"]
  RT --> GN[\"generate_scoped()<br/>_one() schema-repair retry\"]
  GN -. \"QA_GENERATE_PROMPT\" .- P2[(\"prompts/qa.py\")]
  GN --> VF[\"verify_grounding()\"]
  VF -. \"QA_VERIFY_PROMPT\" .- P3[(\"prompts/qa.py\")]
  VF --> A[\"QAAnswer\"]
  style VF fill:#1f2a1a,stroke:#3fb950,color:#fff
  style P1 fill:#241a33,stroke:#9b6bd6,color:#fff
  style P2 fill:#241a33,stroke:#9b6bd6,color:#fff
  style P3 fill:#241a33,stroke:#9b6bd6,color:#fff""",
        "prompts": [
            ("QA_SCOPE_PROMPT", "prompts/qa.py:12", "Extract target_gap + assumed_known from the question."),
            ("QA_GENERATE_PROMPT", "prompts/qa.py:43", "Terse grounded answer over the retrieved set."),
            ("QA_VERIFY_PROMPT", "prompts/qa.py:75", "Flag unsupported claims; report confidence."),
        ],
        "tools": [
            ("retrieve_for_gap", "Qdrant field_textbooks (dense+BM25) + reranker", "Top-4 high-precision retrieval (rerank_top_n=4)."),
            ("generate_scoped → _one (retry)", "nano LLM", "Generate; one schema-repair retry (ADR-005)."),
            ("verify_grounding", "nano LLM", "Grounding verdict over the same sources."),
        ],
        "sources": [
            ("entrypoint", "agents/qa.py:240 (run_qa)"),
            ("scope", "agents/qa.py:74 (extract_scope)"),
            ("retrieve", "agents/qa.py:107 (retrieve_for_gap)"),
            ("generate", "agents/qa.py:165 (generate_scoped, retry at :184)"),
            ("verify", "agents/qa.py:203 (verify_grounding)"),
        ],
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
        "tools_spec": "none", "retrieval": "rerank=False — structural fetch, NOT relevance search (embeddings only resolve fuzzy subtopic → heading)",
        "memory": "off", "validators": "none (optional ground node)",
        "prompt": "prompts/chapter.py — CHAPTER_MAP_FACILITATE_PROMPT", "src": "agents/chapter.py:3-4, modes.py:193-207",
        "purpose": "An ordered, didactic walkthrough of a whole chapter. Fetches the chapter's sections in the book's own order and teaches each one (verbose map, ~250-400 tokens/section), streaming each block as it finishes so you watch the chapter build top to bottom.",
        "when": "Use to learn a chapter section by section in its intended order. Structural, not search-driven — the chapter's section order IS the answer order. Pick Resume instead when you want a compressed recap.",
        "agentic": """flowchart TD
  Q[\"Chapter request\"] --> PS[\"parse-scope\"]
  PS --> FC[\"fetch-chapter (structural, in order)\"]
  FC --> RS[\"resolve-subtopics (fuzzy, nano)\"]
  RS --> MAP[\"map per-section IN ORDER<br/>facilitate = verbose ~250-400 tok\"]
  MAP --> ST[\"stitch\"]
  ST --> GR[\"ground\"]
  GR --> A[\"ChapterDigest (blocks in order)\"]
  style MAP fill:#3a1d1f,stroke:#E5484D,color:#fff""",
        "agentic_cap": "Same pipeline as Resume; only the map prompt + verbosity differ. Order fixed by section_id, never re-sorted by relevance.",
        "funcgraph": """flowchart TD
  E[\"run_chapter()\"] --> PS[\"parse_scope() (CHAPTER_PARSE_PROMPT)\"]
  PS --> RS[\"resolve_subtopics() (CHAPTER_RESOLVE_PROMPT)\"]
  RS --> MP[\"map_sections()<br/>CHAPTER_MAP_FACILITATE_PROMPT (verbose)\"]
  MP --> ST[\"stitch() (CHAPTER_STITCH_PROMPT)\"]
  ST --> GR[\"ground() (CHAPTER_GROUND_PROMPT)\"]
  GR --> A[\"ChapterDigest\"]
  style MP fill:#3a1d1f,stroke:#E5484D,color:#fff""",
        "prompts": [
            ("CHAPTER_PARSE_PROMPT", "prompts/chapter.py:15", "Parse the chapter request into a ChapterScope."),
            ("CHAPTER_RESOLVE_PROMPT", "prompts/chapter.py:46", "Fuzzy-resolve requested subtopics to headings."),
            ("CHAPTER_MAP_FACILITATE_PROMPT", "prompts/chapter.py:70", "Verbose per-section teaching (~250-400 tok)."),
            ("CHAPTER_STITCH_PROMPT", "prompts/chapter.py:114", "Link per-section digests into a flowing whole."),
            ("CHAPTER_GROUND_PROMPT", "prompts/chapter.py:131", "Check the digest against the fetched sections."),
        ],
        "tools": [
            ("fetch chapter sections", "Qdrant field_textbooks (structural, in order)", "Fetch the chapter's sections in book order — NOT a relevance search."),
            ("resolve_subtopics", "embeddings + nano LLM", "Resolve fuzzy subtopic → heading."),
            ("map_sections / stitch / ground", "nano LLM", "Map each section, stitch, ground."),
        ],
        "sources": [
            ("entrypoint", "agents/chapter.py:311 (run_chapter)"),
            ("parse-scope", "agents/chapter.py:87 (parse_scope)"),
            ("resolve-subtopics", "agents/chapter.py:110 (resolve_subtopics)"),
            ("map", "agents/chapter.py:197 (map_sections)"),
            ("stitch", "agents/chapter.py:260 (stitch)"),
            ("ground", "agents/chapter.py:282 (ground)"),
        ],
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
        "tools_spec": "none", "retrieval": "rerank=False — structural fetch, NOT relevance search",
        "memory": "off", "validators": "none (optional ground node)",
        "prompt": "prompts/chapter.py — CHAPTER_MAP_RESUME_PROMPT", "src": "agents/chapter.py:3-4, modes.py:209-223",
        "purpose": "An ordered, compressed recap of a whole chapter. Same structural pipeline as Facilitate, but the map step is terse (~60-100 tokens/section) — a faithful condensed summary in reading order.",
        "when": "Use to review or skim a chapter you have already studied, or to get the gist of one quickly. Pick Facilitate instead when you want a full teaching walkthrough.",
        "agentic": """flowchart TD
  Q[\"Chapter request\"] --> PS[\"parse-scope\"]
  PS --> FC[\"fetch-chapter (structural, in order)\"]
  FC --> RS[\"resolve-subtopics (fuzzy, nano)\"]
  RS --> MAP[\"map per-section IN ORDER<br/>resume = compact ~60-100 tok\"]
  MAP --> ST[\"stitch\"]
  ST --> GR[\"ground\"]
  GR --> A[\"ChapterDigest (blocks in order)\"]
  style MAP fill:#241a33,stroke:#9b6bd6,color:#fff""",
        "agentic_cap": "Identical pipeline to Facilitate; the map prompt is compact instead of verbose.",
        "funcgraph": """flowchart TD
  E[\"run_chapter()\"] --> PS[\"parse_scope() (CHAPTER_PARSE_PROMPT)\"]
  PS --> RS[\"resolve_subtopics() (CHAPTER_RESOLVE_PROMPT)\"]
  RS --> MP[\"map_sections()<br/>CHAPTER_MAP_RESUME_PROMPT (compact)\"]
  MP --> ST[\"stitch() (CHAPTER_STITCH_PROMPT)\"]
  ST --> GR[\"ground() (CHAPTER_GROUND_PROMPT)\"]
  GR --> A[\"ChapterDigest\"]
  style MP fill:#241a33,stroke:#9b6bd6,color:#fff""",
        "prompts": [
            ("CHAPTER_PARSE_PROMPT", "prompts/chapter.py:15", "Parse the chapter request into a ChapterScope."),
            ("CHAPTER_RESOLVE_PROMPT", "prompts/chapter.py:46", "Fuzzy-resolve requested subtopics to headings."),
            ("CHAPTER_MAP_RESUME_PROMPT", "prompts/chapter.py:90", "Compact per-section recap (~60-100 tok)."),
            ("CHAPTER_STITCH_PROMPT", "prompts/chapter.py:114", "Link per-section digests into a flowing whole."),
            ("CHAPTER_GROUND_PROMPT", "prompts/chapter.py:131", "Check the digest against the fetched sections."),
        ],
        "tools": [
            ("fetch chapter sections", "Qdrant field_textbooks (structural, in order)", "Fetch the chapter's sections in book order — NOT a relevance search."),
            ("resolve_subtopics", "embeddings + nano LLM", "Resolve fuzzy subtopic → heading."),
            ("map_sections / stitch / ground", "nano LLM", "Map each section, stitch, ground."),
        ],
        "sources": [
            ("entrypoint", "agents/chapter.py:311 (run_chapter)"),
            ("parse-scope", "agents/chapter.py:87 (parse_scope)"),
            ("resolve-subtopics", "agents/chapter.py:110 (resolve_subtopics)"),
            ("map", "agents/chapter.py:197 (map_sections)"),
            ("stitch", "agents/chapter.py:260 (stitch)"),
            ("ground", "agents/chapter.py:282 (ground)"),
        ],
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
    agentic = m["agentic"].replace('"', "&quot;")

    funcgraph_section = ""
    if m.get("funcgraph"):
        fg = m["funcgraph"].replace('"', "&quot;")
        funcgraph_section = f"""
  <section>
    <h2>Functions workflow</h2>
    <div class="diagram-wrap"><div class="mermaid" data-src="{fg}">{m['funcgraph']}</div></div>
    <p class="caption">Code call-graph — green = LLM-call node, purple = prompt constant, red = synthesis/heavy stage. Verified from the runner source listed below.</p>
  </section>"""

    spt_section = ""
    if m.get("prompts") or m.get("tools") or m.get("sources"):
        prompt_rows = "\n      ".join(
            f'<tr><td><code>{n}</code></td><td><code>{loc}</code></td><td>{d}</td></tr>'
            for n, loc, d in m.get("prompts", [])
        )
        tool_rows = "\n      ".join(
            f'<tr><td><code>{fn}</code></td><td>{hits}</td><td>{d}</td></tr>'
            for fn, hits, d in m.get("tools", [])
        )
        source_rows = "\n      ".join(
            f'<tr><td>{stage}</td><td><code>src/services/chat/{loc}</code></td></tr>'
            for stage, loc in m.get("sources", [])
        )
        spt_section = f"""
  <section>
    <h2>Sources, prompts &amp; tools</h2>
    <h3>Prompts</h3>
    <table><tr><th>Constant</th><th>Location</th><th>Role</th></tr>
      {prompt_rows}
    </table>
    <h3>Tools &amp; retrieval calls</h3>
    <table><tr><th>Function</th><th>Hits</th><th>Purpose</th></tr>
      {tool_rows}
    </table>
    <h3>Source modules</h3>
    <table><tr><th>Stage</th><th>Path</th></tr>
      {source_rows}
    </table>
  </section>"""

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
    <h2>Agentic workflow</h2>
    <div class="diagram-wrap"><div class="mermaid" data-src="{agentic}">{m['agentic']}</div></div>
    <p class="caption">{m['agentic_cap']}</p>
  </section>{funcgraph_section}{spt_section}
  <section>
    <h2>Spec</h2>
    <table>
      <tr><th>Mode id</th><td><code>{m['id']}</code></td></tr>
      <tr><th>Architecture</th><td>{m['arch']}</td></tr>
      <tr><th>Default model</th><td>{m['model']}</td></tr>
      <tr><th>Output schema</th><td><code>{m['schema']}</code></td></tr>
      <tr><th>Tools</th><td>{m['tools_spec']}</td></tr>
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
