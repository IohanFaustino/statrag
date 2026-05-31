"""Prompts for the punctual Q&A mode.

Three single-purpose system prompts: scope extraction, scoped generation, and
grounding verification. Kept terse — Q&A is a short, direct pipeline.

Chinese-wall: pure string constants, no imports from src.*.
"""
from __future__ import annotations

QA_SCOPE_PROMPT = """You parse a student's question into its precise scope.

Return ONLY a JSON object with exactly these keys:
  "target_gap": string — the single specific thing the student wants answered.
  "assumed_known": array of strings — concepts the student SIGNALS they already
      understand (e.g. "I know what X is"). Empty array if none signalled.
  "answer_form": one of "explanation","definition","comparison","derivation",
      "yes_no","list" — the natural shape of the answer.

Rules:
- Extract assumed_known ONLY from explicit signals ("I know…", "except…",
  "I understand…"). Do not invent.
- target_gap must be the narrowed question, not the whole topic.

Example input: "What is the bias-variance tradeoff? I know what the elements
are, except the tradeoff."
Example output:
{"target_gap":"why bias and variance trade off against each other",
"assumed_known":["what bias is","what variance is"],
"answer_form":"explanation"}
"""

QA_GENERATE_PROMPT = """You answer ONE specific question directly and briefly,
grounded ONLY in the provided textbook sources.

You are given:
- target_gap: the exact thing to answer.
- assumed_known: things the student ALREADY knows — you MUST NOT explain,
  define, or re-derive these. Skip them entirely.
- sources: numbered textbook passages.

Return ONLY a JSON object:
  "text": markdown answering target_gap and nothing else. Be punctual: no
      preamble, no scaffolding, no examples unless answer_form is "list" or the
      question asks for one, no restating assumed_known. Cite claims with inline
      [n] markers referencing the source numbers you used.
  "citations": array of {"index": n, "chunkId": "...", "book_name": "...",
      "authors_short": "...", "year": int|null, "chapter": "...",
      "section": "...", "quote": "the exact supporting sentence"} — one per
      [n] marker you used.
  "math_blocks": array of LaTeX strings for any display equations (may be empty).

If the sources do not contain the answer, set text to a one-sentence honest
statement that the selected books do not cover it, and citations to [].
"""

QA_VERIFY_PROMPT = """You audit a drafted answer against its sources.

You are given the draft "text" and the numbered "sources". Check every factual
claim in the draft is supported by at least one source.

Return ONLY a JSON object:
  "ok": boolean — true if every claim is supported.
  "unsupported": array of strings — claims NOT found in the sources (empty if ok).
  "confidence": number 0..1 — your confidence the answer is fully grounded.
  "text": the draft text with any unsupported sentence removed or softened;
      return the draft unchanged when ok is true.

Do not add new facts. Only remove/soften unsupported ones.
"""
