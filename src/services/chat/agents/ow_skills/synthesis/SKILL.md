---
name: synthesis
description: Integrate multiple authors' briefs into one comparative tutor answer that retains every content-bearing key point and compares the authors explicitly.
---

# Synthesis skill

## When to use
When asked to synthesize author briefs (files under `/briefs/`) into a single answer.

## Instructions
1. List `/briefs/` and READ every `/briefs/*.md` file in full before writing.
2. Write ONE coherent answer with a single throughline — not a per-author concatenation.
3. COMPARE the authors explicitly: where they agree, where they differ, and why.
4. Retain every content-bearing key point from the briefs; do not drop facts to be brief.
5. Ground every claim in the briefs. Never invent sources, formulas, or names.
6. Skip "no-info" briefs (a brief stating the source does not discuss the topic).
7. STRUCTURE each subtopic for scanning: open with a short **bold lead sentence**,
   then **bold lead-in bullets** — `- **<claim>** — <explanation>` — one claim per
   line. Use prose only for connective tissue between bullets. Never a wall of text.
8. Math: `$...$` for inline, `$$...$$` for display. Place each `$$display$$` formula
   inside the subtopic it supports — for a worked example, state the model/DGP formula
   in that example's subtopic, not at the end.
9. Figures: keep any `[Fn]` figure marker from the briefs in the subtopic it belongs to.
