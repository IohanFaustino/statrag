"""Prompts for the chapter modes (facilitate + resume).

Six single-purpose system prompts: parse-scope, resolve-subtopics, two map
prompts (teach vs compress), stitch, and ground. Both modes share everything
except which MAP prompt the agent picks.

Chinese-wall: pure string constants, no imports from src.*.
"""
from __future__ import annotations

CHAPTER_PARSE_PROMPT = """You extract the chapter scope from a study request.

You are given the user's message and an optional list of selected book slugs.
Return ONLY a JSON object with exactly these keys:
  "book_slug": string — the book to use. If exactly one slug is selected, use
      it. Otherwise infer from the message; use "" if unknown.
  "chapter_id": string — the chapter id mentioned, normalised like "ch02"
      (zero-padded, lowercase). Use "" if the message names no chapter.
  "requested_subtopics": array of strings — the specific subtopics the user
      asked for, verbatim phrases. Empty array means "the whole chapter".

Do not invent subtopics. Extract only what the user explicitly named.
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
