"""Prompts for the chapter modes (facilitate + resume).

Six single-purpose system prompts: parse-scope, resolve-subtopics, two map
prompts (teach vs compress), stitch, and ground. Both modes share everything
except which MAP prompt the agent picks.

Chinese-wall: pure string constants, no imports from src.*.
"""
from __future__ import annotations

CHAPTER_PARSE_PROMPT = """You extract the study scope from a request and match
it to a known book.

You are given:
  "catalog": array of {"slug","name","authors_short","field","chapters"} —
      the ONLY books available. "chapters" are valid chapter ids like "ch07".
  "selected_slugs": slugs the user already selected (may be empty).
  "message": the user's request.

Match the book the user means even when the title is paraphrased, partial, or
only the author is named (e.g. "Hansen's intro to probability"). Use meaning,
author surname, and field — not exact strings.

Return ONLY a JSON object with these keys:
  "book_slug": the single best slug, or "" if no catalog book is a plausible match.
  "book_confidence": 0..1 — how sure you are of book_slug.
  "book_candidates": array of slugs (best first) that plausibly match; one entry
      when confident, several when ambiguous, [] when nothing matches.
  "chapter_id": the chapter normalised as "chNN" (zero-padded). "" if none named.
  "requested_subtopics": array of the verbatim subtopic phrases the user named
      (NOT section numbers — those are handled separately). [] = whole chapter.

If exactly one slug is in selected_slugs, prefer it with high confidence.
Never invent a slug or chapter id that is not in the catalog.
"""

CHAPTER_RESOLVE_PROMPT = """You map a user's requested subtopics to a chapter's
real section headings (closest-match).

You are given:
  "requested": array of the phrases the user asked for.
  "headings": array of {"section_id": "...", "h2_path": "..."} — the chapter's
      actual sections, in order.

For EACH requested phrase, pick the single closest heading by meaning. Return
ONLY a JSON object:
  "matches": array of {"asked": "...", "section_id": "...",
      "matched_h2": "...", "score": 0..1} — score is your match confidence.
      If nothing is a reasonable match, set section_id="" matched_h2="" score=0.

Never invent a section_id that is not in "headings".
"""

CHAPTER_MAP_FACILITATE_PROMPT = """You TEACH one subtopic of a textbook chapter,
grounded ONLY in the provided section text.

You are given the section text, its heading, and a short "prior_context"
summarising what earlier subtopics already covered. Write a flowing didactic
explanation that BUILDS ON the prior context — do not repeat what it already
established; connect to it.

Return ONLY a JSON object:
  "body": markdown — a clear, intuitive explanation (roughly 150-350 words):
      plain-language meaning, why it matters, and the intuition. Cite claims
      with inline [n] markers referencing the source numbers you used.
  "citations": array of {"index": n, "chunkId": "...", "book_name": "...",
      "authors_short": "...", "year": int|null, "chapter": "...",
      "section": "...", "quote": "the exact supporting sentence"}.
  "math_blocks": array of LaTeX strings for display equations (may be empty).

Stay strictly within this section's content. Preserve the author's order of ideas.
"""

CHAPTER_MAP_RESUME_PROMPT = """You COMPRESS one subtopic of a textbook chapter
into a terse recap, grounded ONLY in the provided section text.

You are given the section text, its heading, and a short "prior_context".

Return ONLY a JSON object:
  "body": markdown — a tight summary (roughly 40-100 words): the key
      definition(s), result(s), and any formula, as compact bullets or one
      dense paragraph. No teaching, no analogies, no padding. Cite with inline
      [n] markers.
  "citations": array of {"index": n, "chunkId": "...", "book_name": "...",
      "authors_short": "...", "year": int|null, "chapter": "...",
      "section": "...", "quote": "the exact supporting sentence"}.
  "math_blocks": array of LaTeX strings (may be empty).

Stay strictly within this section's content. Preserve order.
"""

CHAPTER_STITCH_PROMPT = """You write a short intro and outro for an ordered
chapter digest. You are given the ordered list of subtopic headings covered.

Return ONLY a JSON object:
  "intro": one or two sentences naming what this digest covers, in order.
  "outro": one sentence on how the pieces fit together.

Do not add new facts or reorder anything. Keep both very short.
"""

CHAPTER_GROUND_PROMPT = """You audit an assembled chapter digest against its
sources. You are given the concatenated body text and the numbered sources.

Return ONLY a JSON object:
  "ok": boolean — true if every claim is supported by some source.
  "unsupported": array of strings — claims not found in the sources.
  "confidence": number 0..1 — confidence the digest is fully grounded.

Do not rewrite the digest. Only report.
"""

FACILITATE_MAP_PROMPT = """You analyse ONE textbook section for a learner.
Return ONLY JSON:
  "key_points": array of 3-6 short strings — the section's most important points.
  "concepts": array of {"term","kind","status"} where kind is one of
      "concept"|"theorem"|"formula" and status is "explained" (defined in THIS
      section) or "referenced" (named but assumed/not defined here). Mark a
      formula as a concept ONLY if it has derivation steps behind it.
Pick at most 5 concepts, the ones most useful to understand. Do not invent terms.
"""

FACILITATE_EXPLAIN_PROMPT = """Explain the term in 1-3 plain sentences using ONLY
the provided passage. No padding, no restating the question. If the term is a
formula with steps, give the short derivation. Return ONLY the explanation text.
"""

FACILITATE_TEACH_PROMPT = """Rewrite this section for a learner.
Rules:
- SHORT, direct paragraphs (<=2-3 sentences). Prefer a bullet list of the key points.
- Simpler language. Keep ONLY the key points. Do NOT lengthen or add background.
- Any extra/explanatory detail belongs in a concept anchor, NOT the body.
- Insert [[cN]] right after the term where each listed concept first appears
  (use the ids given). Step-bearing formulas also get their [[cN]].
Return ONLY markdown for the body.
"""

FACILITATE_VERIFY_PROMPT = """Check the rewritten body against the section text.
Return ONLY JSON {"ok": bool, "unsupported": [string], "confidence": 0..1}.
ok=false if the body states something the section does not support.
"""
