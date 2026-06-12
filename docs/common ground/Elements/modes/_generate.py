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
        "note": 'This page documents the <b>current live</b> 4-node Q&amp;A graph. A scoped agentic-retrieval deepagent rebuild is specified but <b>not started</b> — see <code>docs/superpowers/specs/2026-06-05-qa-deepagent-design.md</code>.',
    },
    {
        "id": "facilitate", "name": "Facilitate", "arch": "multi-agent (6-node story pipeline)",
        "schema": "FacilitateStory",
        "model": "nano (per-stage override for parse, map, write via stageModels)",
        "tools_spec": "none", "retrieval": "pure-code resolve_section — closest-match fuzzy title + subtopic overlap, one section only",
        "memory": "off", "validators": "pure-code statement_fidelity (token-recall ≥ 60%) — advisory, never blocks",
        "prompt": "prompts/chapter.py — FACILITATE_STORY_WRITE_PROMPT, FACILITATE_MAP_PROMPT", "src": "agents/facilitate_story.py, modes.py",
        "purpose": "Single-section narrative walkthrough. Resolves exactly ONE section per request, then narrates it as a connected story (hook → movements → takeaway). Formal statements (definition / theorem / proposition / lemma / corollary / remark) are reproduced VERBATIM then unpacked didactically. Concept pills open the ConceptChat side panel (/api/concept/explore) for stateless corpus + Wikipedia follow-up. Pure-code bind and statement-fidelity verify replace the old LLM ground node.",
        "when": "Use to learn a single section in depth — the story arc and verbatim formal statements give you both the precise math and the narrative around it. Send another message for the next section. Pick Resume instead when you want a compressed multi-section chapter recap.",
        "agentic": """flowchart TD
  U[\"User message\"] --> PR[\"parse + resolve scope<br/>LLM · model key map\"]
  PR -->|ambiguous| CL[\"clarify<br/>stop + ask\"]
  PR -->|confident| FE[\"fetch ONE section<br/>pure-code closest-match\"]
  FE --> MAP[\"map · concept extraction<br/>[[cN]] anchors · LLM\"]
  MAP --> WR[\"write story<br/>hook → movements → takeaway<br/>verbatim formal statements\"]
  WR --> BD[\"bind · PURE CODE<br/>provenance + citations verbatim<br/>strip invented anchors\"]
  BD --> VRF[\"verify · PURE CODE<br/>statement fidelity token-recall<br/>sets grounding badge\"]
  VRF --> FS[\"FacilitateStory\"]
  style WR fill:#3a1d1f,stroke:#E5484D,color:#fff
  style BD fill:#1a2233,stroke:#4da6ff,color:#fff
  style VRF fill:#1a2233,stroke:#4da6ff,color:#fff
  style CL fill:#2a1a1a,stroke:#d2624c,color:#fff""",
        "agentic_cap": "One section per request (invariant 44). Bind and verify are pure code — no model call. ConceptChat side panel (/api/concept/explore) is stateless (invariant 46).",
        "funcgraph": """flowchart TD
  E[\"run_facilitate_story()\"] --> PR[\"resolve_book() (FACILITATE_STORY_PARSE_PROMPT / model key map)\"]
  PR -. \"FACILITATE_STORY_PARSE_PROMPT\" .- P1[(\"prompts/chapter.py\")]
  PR --> FE[\"fetch_chapter_sections() + resolve_section() (pure-code)\"]
  FE --> MP[\"_map() (FACILITATE_MAP_PROMPT)\"]
  MP -. \"FACILITATE_MAP_PROMPT\" .- P2[(\"prompts/chapter.py\")]
  MP --> WR[\"_write() (FACILITATE_STORY_WRITE_PROMPT)\"]
  WR -. \"FACILITATE_STORY_WRITE_PROMPT\" .- P3[(\"prompts/chapter.py\")]
  WR --> BD[\"bind_concepts() + strip_unbound_markers() (PURE CODE)\"]
  BD --> VRF[\"statement_fidelity() (PURE CODE)\"]
  VRF --> FS[\"FacilitateStory\"]
  style WR fill:#3a1d1f,stroke:#E5484D,color:#fff
  style BD fill:#1a2233,stroke:#4da6ff,color:#fff
  style VRF fill:#1a2233,stroke:#4da6ff,color:#fff
  style P1 fill:#241a33,stroke:#9b6bd6,color:#fff
  style P2 fill:#241a33,stroke:#9b6bd6,color:#fff
  style P3 fill:#241a33,stroke:#9b6bd6,color:#fff""",
        "prompts": [
            ("FACILITATE_STORY_PARSE_PROMPT", "prompts/chapter.py", "Parse the user message + resolve book/chapter/section (model key: map)."),
            ("FACILITATE_MAP_PROMPT", "prompts/chapter.py", "Extract up to FACILITATE_MAX_CONCEPTS key concepts / theorems / formulas as [[cN]] anchors (LLM stage: map)."),
            ("FACILITATE_STORY_WRITE_PROMPT", "prompts/chapter.py", "Write the story arc: hook → movements[] → takeaway; formal statements reproduced VERBATIM then unpacked (LLM stage: write)."),
        ],
        "tools": [
            ("resolve_book", "nano LLM", "Fuzzy-match user message to a book + chapter in the catalog."),
            ("fetch_chapter_sections + resolve_section", "Qdrant field_textbooks (pure-code closest-match)", "Fetch section headings for the chapter; resolve to a single section_id."),
            ("_map", "nano LLM", "Extract [[cN]] concept/theorem/formula anchors from the source section."),
            ("_write", "nano LLM (write model)", "Generate hook → movements → takeaway narrative with verbatim formal statements."),
            ("bind_concepts / strip_unbound_markers", "pure code (no LLM)", "Attach provenance + StoryCitation verbatim from Source payload; drop invented anchors."),
            ("statement_fidelity", "pure code (no LLM)", "Token-recall check ≥ 60% per formal statement; sets grounding.ok."),
            ("/api/concept/explore", "nano LLM (stateless endpoint)", "ConceptChat side panel — corpus + Wikipedia context for a clicked concept pill."),
        ],
        "sources": [
            ("entrypoint", "agents/facilitate_story.py (run_facilitate_story)"),
            ("parse + resolve", "agents/facilitate_story.py (resolve_book / _scope.py resolve_section)"),
            ("map", "agents/facilitate_story.py (_map)"),
            ("write", "agents/facilitate_story.py (_write / _parse_draft)"),
            ("bind", "agents/facilitate_story.py (bind_concepts / strip_unbound_markers)"),
            ("verify", "agents/facilitate_story.py (statement_fidelity)"),
            ("concept endpoint", "api.py (POST /api/concept/explore)"),
        ],
        "fields": [
            ("mode", "\"facilitate_story\" — renderer discriminator (legacy FacilitateDigest keeps mode \"facilitate\")."),
            ("scope", "ChapterScope: book_slug, chapter_id, section_id resolved."),
            ("hook", "Opening narrative sentence setting up the section."),
            ("movements[]", "List of Movement objects: prose | formal (FormalStatement with verbatim statement + didactic unpack)."),
            ("takeaway", "Closing synthesis tying the story back to the section's key insight."),
            ("concepts[]", "ConceptAnchor list: [[cN]] id, term, provenance assembled verbatim from Source payload."),
            ("citations[]", "StoryCitation list built verbatim from Source object fields — never model-authored."),
            ("math_blocks[]", "Rendered LaTeX blocks extracted by the write stage."),
            ("grounding", "{ok, unsupported[], confidence} — set by pure-code statement_fidelity; advisory."),
        ],
        "fields_note": "schemas/output.py (FacilitateStory). Legacy FacilitateDigest schema retained for pre-remake conversations. Invariants 44–47.",
        "note": 'The old chapter-loop pipeline (<code>run_chapter / ChapterDigest / CHAPTER_MAP_FACILITATE_PROMPT</code>) is <b>retired for facilitate</b> as of 2026-06-12. <code>FacilitateDigest</code> conversations still render via the legacy card. See <a href="../../services/chat-features/53-facilitate-concept-map.md">doc 53</a>.',
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
    note_section = ""
    if m.get("note"):
        note_section = f'\n  <section><div class="card" style="border-left:3px solid var(--accent)"><p style="margin:0">{m["note"]}</p></div></section>'

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
</header>{note_section}
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
