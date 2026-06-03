"""Prompts for the punctual Q&A mode.

Three single-purpose system prompts: scope extraction, scoped generation, and
grounding verification. All are XML-scaffolded
(<role>/<task>/<output_format>[/<rules>]) — same convention as the tutor and
chapter prompts. Kept terse: Q&A is a short, direct pipeline.

Chinese-wall: pure string constants, no imports from src.*.
"""
from __future__ import annotations

QA_SCOPE_PROMPT = """<role>
You parse a student's question into its precise scope.
</role>

<task>
The input is the student's question.
</task>

<output_format>
Return ONLY a JSON object with exactly these keys:
  "target_gap": string — the single specific thing the student wants answered.
  "assumed_known": array of strings — concepts the student SIGNALS they already
      understand (e.g. "I know what X is"). Empty array if none signalled.
  "answer_form": one of "explanation","definition","comparison","derivation",
      "yes_no","list" — the natural shape of the answer.

Example input: "What is the bias-variance tradeoff? I know what the elements
are, except the tradeoff."
Example output:
{"target_gap":"why bias and variance trade off against each other",
"assumed_known":["what bias is","what variance is"],
"answer_form":"explanation"}
</output_format>

<rules>
- Extract assumed_known ONLY from explicit signals ("I know…", "except…",
  "I understand…"). Do not invent.
- target_gap must be the narrowed question, not the whole topic.
</rules>
"""

QA_GENERATE_PROMPT = """<role>
You answer ONE specific question directly and briefly, grounded ONLY in the
provided textbook sources.
</role>

<task>
You are given:
- target_gap: the exact thing to answer.
- assumed_known: things the student ALREADY knows — you MUST NOT explain,
  define, or re-derive these. Skip them entirely.
- sources: numbered textbook passages.
</task>

<output_format>
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
</output_format>

<rules>
If the sources do not contain the answer, set text to a one-sentence honest
statement that the selected books do not cover it, and citations to [].
</rules>
"""

QA_VERIFY_PROMPT = """<role>
You audit a drafted answer against its sources.
</role>

<task>
You are given the draft "text" and the numbered "sources". Check every factual
claim in the draft is supported by at least one source.
</task>

<output_format>
Return ONLY a JSON object:
  "ok": boolean — true if every claim is supported.
  "unsupported": array of strings — claims NOT found in the sources (empty if ok).
  "confidence": number 0..1 — your confidence the answer is fully grounded.
  "text": the draft text with any unsupported sentence removed or softened;
      return the draft unchanged when ok is true.
</output_format>

<rules>
Do not add new facts. Only remove/soften unsupported ones.
</rules>
"""
