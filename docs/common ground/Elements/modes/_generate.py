#!/usr/bin/env python3
"""Generate the per-mode doc pages.

Source of truth: src/services/chat/modes.py (ModeSpec registry, register_all_modes),
agents/qa.py + agents/chapter.py (runners), schemas/output.py. Static output only —
maintenance convenience, not a build dependency. Re-run after the mode registry changes:

    cd "docs/common ground/Elements/modes" && python3 _generate.py

Emits (relative to this dir): index.html + one <mode>.html per registered mode.
Nav lives in ../sidebar.js (hand-maintained toggle config) — this script does NOT
touch it.
"""
from __future__ import annotations
import html
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Verified from modes.py:153-225 (ModeSpec fields) + the named runners.
# fields: id, name, icon, arch, schema, tools, retrieval, model, validators, memory,
#         runner, runner_src, purpose
MODES = [
    ("tutor", "Tutor", "book", "single", "TutorAnswer", "retrieve",
     "rerank=False (gated until M4)", "nano", "citation", "auto",
     "Single-agent tool loop. The rich deep-tutor pipeline (see the Chat &amp; deep-tutor page) "
     "produces the structured TutorAnswer — query planner → multi-query retrieval → density/diversity/rerank "
     "→ coverage → figure judge → planner-orchestrator → drafting workflow → vision explain.",
     "agents/deep_tutor.py · prompts/tutor.py (TUTOR_INSTRUCTIONS)",
     "Default didactic Q&amp;A over the corpus. Deep, multi-author synthesis with citations, figures, and math. Memory on (auto)."),
    ("qa", "Q&amp;A", "target", "multi", "QAAnswer", "—",
     "rerank=True, rerank_top_n=4", "nano", "—", "off",
     "Four-node graph: scope → retrieve → scoped generate → verify / finalise.",
     "agents/qa.py · prompts/qa.py (QA_GENERATE_PROMPT)",
     "Punctual, scoped Q&amp;A. Extracts the target gap + assumed-known, retrieves narrowly (top 4), "
     "generates a terse grounded answer, then verifies grounding. No memory."),
    ("facilitate", "Facilitate", "graduation-cap", "multi", "ChapterDigest", "—",
     "rerank=False", "nano", "—", "off",
     "Chapter pipeline: parse-scope → fetch-chapter → resolve-subtopics → map (per section, in order) "
     "→ stitch → ground. Order is fixed structurally by section_id — a structural fetch, not a search.",
     "agents/chapter.py · prompts/chapter.py (CHAPTER_MAP_FACILITATE_PROMPT)",
     "Ordered didactic walkthrough of a chapter — teach it section by section in the book's own order."),
    ("resume", "Resume", "file-text", "multi", "ChapterDigest", "—",
     "rerank=False", "nano", "—", "off",
     "Same chapter pipeline as facilitate (parse-scope → fetch-chapter → resolve-subtopics → map → stitch → ground), "
     "different map prompt. Structural fetch, order preserved by section_id.",
     "agents/chapter.py · prompts/chapter.py (CHAPTER_MAP_RESUME_PROMPT)",
     "Ordered compressed recap of a chapter — a faithful, condensed summary in reading order."),
]

# Chapter-mode env knobs (chapter.py:45-48), shown on facilitate + resume.
CHAPTER_KNOBS = [
    ("CHAPTER_RESOLVE", "1", "LLM-resolve requested subtopics that did not match a heading by string."),
    ("CHAPTER_MAX_SECTIONS", "30", "Cap on sections mapped per chapter."),
    ("CHAPTER_STITCH", "1", "Run the stitch pass that links per-section digests into a flowing whole."),
    ("CHAPTER_GROUND", "1", "Run the grounding pass that checks the digest against the fetched sections."),
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


def mode_page(m: tuple) -> str:
    (mid, name, icon, arch, schema, tools, retrieval, model, validators, memory,
     runner, runner_src, purpose) = m
    knobs = ""
    if mid in ("facilitate", "resume"):
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
    <p class="caption">Source: <code>src/services/chat/agents/chapter.py:45-48</code>. Per-stage model override via <code>CHAPTER_&lt;STAGE&gt;_MODEL</code>.</p>
  </section>"""
    body = f"""<header>
  <h1><span class="accent">{name}</span> mode <span class="pill">{arch}-agent</span></h1>
  <div class="sub">{purpose}</div>
</header>
<main>
  <section>
    <h2>Spec</h2>
    <table>
      <tr><th>Mode id</th><td><code>{mid}</code></td></tr>
      <tr><th>Architecture</th><td>{arch}</td></tr>
      <tr><th>Output schema</th><td><code>{schema}</code></td></tr>
      <tr><th>Tools</th><td>{tools}</td></tr>
      <tr><th>Retrieval flags</th><td>{retrieval}</td></tr>
      <tr><th>Model tier</th><td>{model}</td></tr>
      <tr><th>Post-validators</th><td>{validators}</td></tr>
      <tr><th>Memory</th><td>{memory}</td></tr>
    </table>
    <p class="caption">Source: <code>src/services/chat/modes.py</code> (ModeSpec registry).</p>
  </section>
  <section>
    <h2>Runner</h2>
    <div class="card"><p style="margin:0">{runner}</p></div>
    <p class="caption">Code: <code>{runner_src}</code>.</p>
  </section>{knobs}
</main>"""
    return page_shell(name.replace("&amp;", "&"), body)


def index_page() -> str:
    rows = []
    for m in MODES:
        mid, name, icon, arch, schema = m[0], m[1], m[2], m[3], m[4]
        purpose = m[12]
        rows.append(
            f'<tr><td><a href="{mid}.html">{name}</a></td>'
            f'<td>{arch}</td><td><code>{schema}</code></td><td>{purpose}</td></tr>'
        )
    table = "\n      ".join(rows)
    body = f"""<header>
  <h1>statrag — <span class="accent">Modes</span></h1>
  <div class="sub">The chat modes you can pick. Each is a registered ModeSpec with its own runner + output schema. <span class="pill">4 modes</span></div>
</header>
<main>
  <section>
    <h2>All modes</h2>
    <table>
      <tr><th>Mode</th><th>Arch</th><th>Output schema</th><th>Purpose</th></tr>
      {table}
    </table>
    <p class="caption">Source of truth: <code>src/services/chat/modes.py</code> (register_all_modes). Click a mode for its full spec + runner.</p>
  </section>
  <section>
    <h2>Two families</h2>
    <div class="card"><p style="margin:0 0 8px"><b>Search modes</b> (tutor, qa) retrieve by relevance to a question. <b>Chapter modes</b> (facilitate, resume) do a <b>structural fetch</b> of a whole chapter and emit a <code>ChapterDigest</code> in the book's own section order — not a search.</p></div>
  </section>
</main>"""
    return page_shell("Modes", body)


def main() -> None:
    (HERE / "index.html").write_text(index_page())
    n = 0
    for m in MODES:
        (HERE / f"{m[0]}.html").write_text(mode_page(m))
        n += 1
    print(f"wrote modes/index.html + {n} mode pages")


if __name__ == "__main__":
    main()
