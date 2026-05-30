"""Deep tutor pipeline v2 — multi-aspect schema + latency optimisations.

Pipeline:

    parallel:
      a) extract_concepts(query)              [nano, ~250ms]
      b) wide RRF candidate pull (no rerank)  [Qdrant, ~400ms]

    once both done:
      c) density_score_candidates(...)
      d) expand top sections via scroll       [Qdrant, ~200ms]
      e) cross-encoder rerank                 [~150ms warm; cold ~5s]

    draft (single LLM call, streamed)
      f) chat.completions.parse with response_format=DeepTutorAnswer
         OR streaming json_object then validated
                                              [nano, ~6-10s]

    [optional] critique + refine — gated by TUTOR_DEEP_CRITIQUE=1.

    finalize: convert DeepTutorAnswer -> TutorAnswer w/ assembled
    markdown + ``aspects`` dict + citation reconciliation.

Performance levers:
    - reranker warmed at module import (avoids 5-8s cold-load)
    - parallel extract + retrieve via asyncio.gather
    - critique loop OFF by default
    - tighter density-stage caps (top 3 sections, 6 chunks/section)
    - true OpenAI streaming for the draft (first token < 2s)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, AsyncIterator, NamedTuple

import openai as _openai

from src.core.config import settings
from src.services.chat._fences import strip_fences
from src.services.chat.agents.coverage import (
    COVERAGE_ON,
    assess_coverage,
    fill_missing_facets,
)
from src.services.chat.prompts.deep_tutor import (
    ASPECT_HEADINGS,
    CRITIQUE_PROMPT,
    DEEP_TUTOR_INSTRUCTIONS,
    EXTRACT_CONCEPTS_BUDGET_PROMPT,
    EXTRACT_CONCEPTS_PROMPT,
    ORGANIZER_PREAMBLE,
    SYNTHESIS_PLAN_PROMPT,
    assemble_markdown,
    format_source_bundle,
)
from src.services.chat.agents.image_judge import (
    judge_image_candidates,
    resolve_image_for_vision,
)
from src.services.chat.llm.base import ChatMessage
from src.services.chat.llm.router import get_llm, list_providers
from src.services.chat.retrievers.density import (
    _PseudoPoint,
    _count_occurrences,
    _fetch_neighbor_chunks,
    _fetch_section_chunks,
    _section_score,
    _source_to_pseudo_point,
)
from src.services.chat.retrievers.diversity import (
    AuthorMeta,
    author_key,
    build_author_filter_from_candidates,
    diversify_section_keys,
)
from src.services.chat.retrievers.image_density import fetch_image_candidates
from src.services.chat.retrieval import _point_to_source, hybrid_search
from src.services.chat.books import collections_for_books, list_books
from src.services.chat.rerankers import get_reranker
from src.services.chat.schemas import ChatRequest, RetrievalMetadata, Source
from src.services.chat.schemas.output import (
    DeepTutorAnswer,
    SynthesisPlan,
    TutorAnswer,
    TutorCitation,
)

logger = logging.getLogger(__name__)


# LaTeX repair: LLMs frequently emit `\theta` inside a JSON string instead of
# `\\theta`. `json.loads` then silently converts `\t` to tab, leaving `heta`.
# Pre-pass any raw model JSON to double single-backslash latex commands.
_LATEX_CMDS = (
    r"(?:theta|nabla|alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|iota|"
    r"kappa|lambda|mu|nu|xi|pi|rho|sigma|tau|upsilon|phi|varphi|chi|psi|omega|"
    r"Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Upsilon|Phi|Psi|Omega|"
    r"mathbb|mathcal|mathbf|mathrm|mathit|mathsf|mathtt|"
    r"hat|tilde|bar|vec|dot|ddot|widehat|widetilde|overline|underline|"
    r"frac|sqrt|sum|int|prod|lim|sup|inf|min|max|"
    r"log|ln|exp|sin|cos|tan|cot|sec|csc|"
    r"operatorname|text|textbf|textit|textrm|emph|"
    r"leq|geq|neq|approx|equiv|sim|propto|cdot|times|div|pm|mp|"
    r"quad|qquad|partial|infty|to|leftarrow|rightarrow|leftrightarrow|"
    r"left|right|begin|end|over|"
    r"langle|rangle|lceil|rceil|lfloor|rfloor|"
    r"forall|exists|in|notin|subset|supset|cup|cap|emptyset|"
    r"binom|choose|sout|cancel|colon|ldots|cdots|vdots|ddots)"
)
_LATEX_REPAIR_RE = re.compile(r"(?<!\\)\\(" + _LATEX_CMDS + r")\b")


def _loads_tolerant_json_object(raw: str) -> dict | None:
    """Best-effort JSON-object parse for chatty providers (esp. deepseek-reasoner,
    which prefixes its answer with chain-of-thought prose, may wrap the object
    in markdown, may trail with explanatory text, and frequently truncates at
    max_tokens leaving an unterminated string and unbalanced braces).

    Strategy, in order:
      1. ``json.loads(raw)`` — clean case.
      2. ``json.loads(_repair_latex_escapes(raw))`` — fix bare-backslash latex.
      3. Slice the substring from the first ``{`` to the last ``}`` (greedy
         outer braces) and retry both raws.
      4. Truncation repair: walk the prefix from the first ``{``, close any
         open string with ``"``, then close every still-open brace/bracket.
         Drop trailing partial-key state. Last-ditch salvage so a payload
         truncated at max_tokens still yields the aspects that did finish.
    Returns ``None`` if every attempt fails — caller logs and degrades.
    """
    if not raw:
        return None

    def _try(s: str) -> dict | None:
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else None
        except Exception:  # noqa: BLE001
            return None

    for candidate in (raw, _repair_latex_escapes(raw)):
        got = _try(candidate)
        if got is not None:
            return got

    first = raw.find("{")
    last = raw.rfind("}")
    if first == -1:
        return None
    if last > first:
        sliced = raw[first : last + 1]
        for candidate in (sliced, _repair_latex_escapes(sliced)):
            got = _try(candidate)
            if got is not None:
                return got

    # Truncation salvage: scan the prefix and close anything still open.
    prefix = raw[first:]
    in_str = False
    esc = False
    stack: list[str] = []
    last_complete = -1
    for i, ch in enumerate(prefix):
        if in_str:
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = False
                last_complete = i
            continue
        if ch == '"':
            in_str = True
            continue
        if ch in "{[":
            stack.append(ch)
            continue
        if ch in "}]":
            if stack and ((ch == "}" and stack[-1] == "{") or (ch == "]" and stack[-1] == "[")):
                stack.pop()
                last_complete = i
    repaired = prefix
    if in_str:
        # Drop the unterminated string entirely by trimming back to the last
        # known-good position (a closed string/brace) and then closing pairs.
        if last_complete >= 0:
            repaired = prefix[: last_complete + 1]
            stack = []
            in_str = False
            esc = False
            for ch in repaired:
                if in_str:
                    if esc:
                        esc = False
                        continue
                    if ch == "\\":
                        esc = True
                        continue
                    if ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                    continue
                if ch in "{[":
                    stack.append(ch)
                    continue
                if ch in "}]" and stack:
                    if (ch == "}" and stack[-1] == "{") or (ch == "]" and stack[-1] == "["):
                        stack.pop()
        else:
            repaired = prefix + '"'
    # Strip any dangling partial key/value at the tail so we can cleanly
    # close. Walk back past whitespace, then drop a trailing
    # ``"key":`` / ``"key": value,`` / lone ``,`` / lone ``:`` so the
    # close-brace produces a syntactically valid object.
    repaired = re.sub(r"[\s,]+$", "", repaired)
    repaired = re.sub(r'(?:"[^"]*"\s*:\s*[^,{}\[\]]*)$', "", repaired)
    repaired = re.sub(r"[\s,:]+$", "", repaired)
    # Drop a trailing bare key (``"key"`` with no value).
    repaired = re.sub(r',?\s*"[^"]*"\s*$', "", repaired)
    repaired = re.sub(r"[\s,:]+$", "", repaired)
    # Close every still-open container, innermost first.
    for opener in reversed(stack):
        repaired += "}" if opener == "{" else "]"
    for candidate in (repaired, _repair_latex_escapes(repaired)):
        got = _try(candidate)
        if got is not None:
            return got
    return None


def _repair_latex_escapes(raw: str) -> str:
    """Double single backslashes preceding known latex commands inside a JSON
    raw string. Safe-by-default: only touches recognised command names and
    only when not already escaped."""
    if not raw or "\\" not in raw:
        return raw
    return _LATEX_REPAIR_RE.sub(r"\\\\\1", raw)


# Post-repair: when raw JSON could not be pre-processed (OpenAI's structured
# stream parses internally), the `\t`, `\n`, `\b`, `\f`, `\r` escapes have
# already collapsed control chars onto latex command stems — the first
# letter of the command was consumed by the JSON escape (e.g. `\theta` →
# TAB + `heta`). Reattach `\` + restore the full command name.
# Each pair is (stem-after-escape, full-command-name).
_POST_REPAIR_TABLE: list[tuple[str, list[tuple[str, str]]]] = [
    ("\t", [
        ("heta", "theta"), ("au", "tau"), ("imes", "times"),
        ("extbf", "textbf"), ("extit", "textit"), ("extrm", "textrm"),
        ("ext", "text"), ("ilde", "tilde"), ("op", "top"), ("o", "to"),
    ]),
    ("\n", [
        ("abla", "nabla"), ("eq", "neq"), ("eg", "neg"),
        ("otin", "notin"), ("ot", "not"), ("e", "ne"), ("u", "nu"),
    ]),
    ("\b", [
        ("ar", "bar"), ("eta", "beta"), ("inom", "binom"),
        ("egin", "begin"), ("m", "bm"), ("ot", "bot"),
    ]),
    ("\f", [
        ("rac", "frac"), ("orall", "forall"), ("box", "fbox"),
    ]),
    ("\r", [
        ("ho", "rho"), ("angle", "rangle"),
        ("ightarrow", "rightarrow"), ("ight", "right"),
    ]),
]


def _repair_latex_post(s: str) -> str:
    if not s:
        return s
    out = s
    for ch, pairs in _POST_REPAIR_TABLE:
        if ch not in out:
            continue
        for stem, cmd in pairs:
            # Word-boundary check: only replace if the stem is a standalone
            # token (next char is not alpha-numeric) to avoid e.g. `<TAB>extra`
            # matching the `ext` stem and producing `\textra`.
            needle = ch + stem
            idx = 0
            while True:
                pos = out.find(needle, idx)
                if pos < 0:
                    break
                after = pos + len(needle)
                if after >= len(out) or not out[after].isalnum():
                    out = out[:pos] + "\\" + cmd + out[after:]
                    idx = pos + 1 + len(cmd)
                else:
                    idx = pos + 1
    return out


# ---------------------------------------------------------------------------
# Bare-LaTeX wrapper: bundle contiguous runs of math tokens in ``$...$`` so
# KaTeX picks them up even when the LLM forgot to delimit. Operates on the
# already-repaired aspect text.
# ---------------------------------------------------------------------------

# A latex command followed by optional braced args / sub-sup is a single
# math token. Brackets, parens, equals, operators, comparators, comma,
# digits, single letters, ``^`` / ``_`` subscripts, and the ``\\big``-style
# delimiters all count too.
_MATH_TOK = (
    r"(?:"
    # latex command with optional braced args + sub/sup
    r"\\[a-zA-Z]+(?:\{[^{}]*\})*(?:[_^](?:\{[^{}]*\}|[A-Za-z0-9*]))*"
    r"|"
    # isolated single math letter (not adjacent to another letter)
    r"(?<![A-Za-z])[A-Za-z](?![A-Za-z])"
    r"|"
    # numeric literal
    r"\d+(?:\.\d+)?"
    r"|"
    # math operators / punctuation that links tokens
    r"[=+\-*/<>|,^_]"
    r"|"
    # short balanced ()/[] groups containing math hints
    r"\([^()]*[\\=^_][^()]*\)"
    r"|"
    r"\[[^\[\]]*[\\=^_][^\[\]]*\]"
    r")"
)
_MATH_RUN_RE = re.compile(_MATH_TOK + r"(?:\s*" + _MATH_TOK + r")*")


def _wrap_bare_math(s: str) -> str:
    """Wrap contiguous bare-latex math runs in ``$...$`` delimiters.

    Skips runs already inside ``$...$`` or ``$$...$$``. Conservative: only
    wraps runs that contain at least one ``\\command`` (so plain English
    with stray punctuation is untouched).
    """
    if not s or "\\" not in s:
        return s
    # Split by existing math delimiters so we don't re-wrap.
    parts = re.split(r"(\$\$[^$]+\$\$|\$[^$]+\$)", s)
    out_parts: list[str] = []
    for part in parts:
        if part.startswith("$"):
            out_parts.append(part)
            continue
        out_parts.append(_wrap_bare_math_segment(part))
    return "".join(out_parts)


# ---------------------------------------------------------------------------
# Figure → aspect placement
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "this", "that", "their", "these",
    "those", "into", "about", "above", "below", "over", "under", "between",
    "while", "where", "when", "which", "what", "have", "been", "being",
    "more", "less", "than", "then", "such", "also", "would", "could", "should",
    "must", "very", "much", "many", "some", "most", "each", "other", "into",
    "figure", "figures", "table", "shows", "show", "example",
})


def _word_tokens(s: str) -> set[str]:
    """Lowercase content tokens of length ≥ 4 minus stopwords."""
    if not s:
        return set()
    toks = re.findall(r"[A-Za-z][A-Za-z\-]{3,}", s.lower())
    return {t for t in toks if t not in _STOPWORDS}


def _score_aspect_for_figure(
    aspect_body: str, fig_tokens: set[str], fig_hint: str | None, aspect_key: str
) -> float:
    """Higher = better match. Token-overlap fraction + small bonus when the
    judge-provided aspect_hint agrees with this aspect."""
    body_tokens = _word_tokens(aspect_body)
    if not body_tokens or not fig_tokens:
        overlap = 0.0
    else:
        inter = fig_tokens & body_tokens
        overlap = len(inter) / max(len(fig_tokens), 1)
    bonus = 0.10 if (fig_hint and fig_hint == aspect_key) else 0.0
    return overlap + bonus


def _score_example_relevance(aspects: dict[str, str]) -> float:
    """Audit signal in [0,1]: how well the ``example_intuition`` aspect
    illustrates the concept it follows. Lexical overlap of its tokens with
    the union of definition + formal_statement tokens. Cheap,
    deterministic, no extra LLM call. 0.0 when either side is empty."""
    ex_tokens = _word_tokens(aspects.get("example_intuition", ""))
    concept_tokens = (
        _word_tokens(aspects.get("definition", ""))
        | _word_tokens(aspects.get("formal_statement", ""))
    )
    if not ex_tokens or not concept_tokens:
        return 0.0
    return round(len(ex_tokens & concept_tokens) / len(ex_tokens), 3)


def _norm_for_match(s: str) -> str:
    """Lowercase, drop markdown/latex punctuation, collapse whitespace —
    so a blockquote can be compared to source text robustly."""
    s = s.lower()
    s = re.sub(r"[*_`$\\>]", " ", s)        # markdown / latex delimiters
    s = re.sub(r"\[\d+\]", " ", s)          # citation markers
    s = re.sub(r"[^a-z0-9 ]+", " ", s)      # punctuation incl. commas
    return " ".join(s.split())


def _verbatim_blockquote_match(formal_statement: str, sources: list[Source]) -> float | None:
    """Audit #7: if ``formal_statement`` contains a ``>`` blockquote (a
    claimed verbatim theorem), measure how well it matches actual source
    text. Returns the best score in [0,1] (1.0 = clean substring), or
    ``None`` when there is no blockquote to check."""
    quote_lines = [
        m.group(1)
        for line in formal_statement.splitlines()
        if (m := re.match(r"^\s*>\s?(.*)$", line))
    ]
    quote = _norm_for_match(" ".join(quote_lines))
    if not quote:
        return None
    q_tokens = quote.split()
    if not q_tokens:
        return None
    best = 0.0
    for src in sources:
        body = _norm_for_match(src.chunk or src.excerpt or "")
        if not body:
            continue
        if quote in body:
            return 1.0
        # token-recall: fraction of quote tokens present in this source
        body_set = set(body.split())
        recall = sum(1 for t in q_tokens if t in body_set) / len(q_tokens)
        best = max(best, recall)
    return round(best, 3)


async def _embed_relevance(aspects: dict[str, str]) -> float | None:
    """Audit #8 (upgrade): semantic relevance of the ``example_intuition``
    aspect to the concept (definition + formal_statement) via embedding
    cosine. Best-effort: returns ``None`` on empty input or any failure so
    the caller can fall back to the lexical scorer."""
    example = (aspects.get("example_intuition") or "").strip()
    concept = "\n".join(
        (aspects.get(k) or "") for k in ("definition", "formal_statement")
    ).strip()
    if not example or not concept:
        return None
    try:
        from src.core.config import settings

        oa = _async_client()
        resp = await oa.embeddings.create(
            model=settings.embedding_model, input=[example[:6000], concept[:6000]]
        )
        a = resp.data[0].embedding
        b = resp.data[1].embedding
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if na == 0 or nb == 0:
            return None
        return round(max(0.0, dot / (na * nb)), 3)
    except Exception:  # noqa: BLE001
        logger.exception("embedding relevance failed; falling back to lexical")
        return None


# TL;DR should stay concise; never auto-target it.
_PLACEMENT_EXCLUDE = {"tldr"}


def _choose_target_aspect(
    fig: object, final_aspects: dict[str, str], fallback: str
) -> str:
    """Pick the aspect whose prose has the highest token overlap with the
    figure caption + judge_reason. Excludes TL;DR. Falls back to
    ``aspect_hint`` then to *fallback* when nothing has signal."""
    cap = (getattr(fig, "caption", "") or "")
    reason = (getattr(fig, "judge_reason", "") or "")
    fig_tokens = _word_tokens(cap + " " + reason)
    hint = getattr(fig, "aspect_hint", None)
    best_key = hint if (
        hint and hint not in _PLACEMENT_EXCLUDE
        and final_aspects.get(hint, "").strip()
    ) else fallback
    best_score = -1.0
    for key in ASPECT_HEADINGS:
        if key in _PLACEMENT_EXCLUDE:
            continue
        body = final_aspects.get(key, "")
        if not body.strip():
            continue
        s = _score_aspect_for_figure(body, fig_tokens, hint, key)
        if s > best_score:
            best_score = s
            best_key = key
    if best_score <= 0.0:
        if hint and hint not in _PLACEMENT_EXCLUDE and final_aspects.get(hint, "").strip():
            return hint
        return fallback
    return best_key


# ---------------------------------------------------------------------------
# Lead-sentence templates (role-aware, varied)
# ---------------------------------------------------------------------------

_LEAD_TEMPLATES: dict[str, list[str]] = {
    "diagram": [
        "The diagram below from *{label}* lays out {topic}:",
        "Visualised in *{label}*, the structure of {topic} is:",
        "The schematic below ({label}) captures {topic}:",
    ],
    "graph": [
        "The plot below from *{label}* shows how {topic}:",
        "In *{label}*, the empirical pattern for {topic} is:",
        "The graph below ({label}) illustrates {topic}:",
    ],
    "chart": [
        "The chart below from *{label}* summarises {topic}:",
        "From *{label}*, the chart of {topic}:",
    ],
    "table": [
        "The table below from *{label}* lists {topic}:",
        "Tabulated in *{label}*, {topic}:",
    ],
    "equation": [
        "The equation below from *{label}* formalises {topic}:",
        "Stated formally in *{label}*, {topic}:",
    ],
    "photo": [
        "The image below from *{label}* shows {topic}:",
    ],
}
_LEAD_GENERIC: list[str] = [
    "The figure below from *{label}* illustrates {topic}:",
    "From *{label}*, the {role} below depicts {topic}:",
    "Drawn from *{label}*, this {role} captures {topic}:",
]
_LEAD_NO_TOPIC: list[str] = [
    "The {role} below from *{label}*:",
    "Reproduced from *{label}*:",
    "From *{label}*:",
]


def _build_lead(role: str, label: str, topic: str, seq: int) -> str:
    # Normalise unusable role labels so the prose never reads "The other
    # below from …" or "The below from …".
    role_norm = (role or "").lower().strip()
    if role_norm in ("", "other", "none", "unknown"):
        role_norm = "figure"
    role_display = role_norm
    has_topic = bool(topic and topic != "the concept above")
    if not has_topic:
        bank = _LEAD_NO_TOPIC
    else:
        bank = _LEAD_TEMPLATES.get(role_norm, _LEAD_GENERIC)
    tmpl = bank[seq % len(bank)]
    return tmpl.format(label=label, topic=topic, role=role_display)


def _wrap_bare_math_segment(seg: str) -> str:
    # Find every match that contains a backslash command; wrap it.
    def repl(m: re.Match) -> str:
        tok = m.group(0)
        if "\\" not in tok:
            return tok
        # Trim trailing whitespace/punctuation that shouldn't go inside math.
        trail = ""
        while tok and tok[-1] in " ,.;:":
            trail = tok[-1] + trail
            tok = tok[:-1]
        if not tok:
            return trail
        return "$" + tok + "$" + trail

    return _MATH_RUN_RE.sub(repl, seg)


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

_ENABLE_CRITIQUE = os.environ.get("TUTOR_DEEP_CRITIQUE", "0") == "1"
_MAX_REFINE_ITERS = int(os.environ.get("TUTOR_DEEP_MAX_REFINE", "1"))
_TOP_SECTIONS = int(os.environ.get("TUTOR_DEEP_TOP_SECTIONS", "4"))
_FINAL_TOP_N = int(os.environ.get("TUTOR_DEEP_FINAL_TOP_N", "8"))
_MAX_CHUNKS_PER_SECTION = int(os.environ.get("TUTOR_DEEP_MAX_CHUNKS_PER_SECTION", "6"))
_MAX_COMPLETION_TOKENS = int(os.environ.get("TUTOR_DEEP_MAX_TOKENS", "16000"))
# Per-provider output-token caps. Groq enforces an 8192 ceiling on
# `max_completion_tokens` for hosted Llama models; exceeding it returns a 400.
_GROQ_MAX_COMPLETION_TOKENS = 8192


def _cap_max_tokens(model_id: str | None) -> int:
    """Return the per-model output-token cap, clamped to provider limits."""
    from src.services.chat.llm.router import GROQ_MODEL_IDS  # noqa: PLC0415
    if model_id and model_id in GROQ_MODEL_IDS:
        return min(_MAX_COMPLETION_TOKENS, _GROQ_MAX_COMPLETION_TOKENS)
    return _MAX_COMPLETION_TOKENS


# Groq-specific prompt addendum. Llama 4 Scout and the gpt-oss models default
# to inline math (`$...$`) and frequently drop backslashes from LaTeX commands
# when emitting JSON strings (`sigma` instead of `\sigma`). This addendum
# corrects both. See `docs/services/chat-features/<NN>-groq-parity.md`.
_GROQ_PROMPT_ADDENDUM = """

<role_addendum>
You are now also responsible for KaTeX-safe LaTeX serialisation. Llama-class
models drop backslashes when emitting JSON — these rules prevent that.
</role_addendum>

<context_addendum>
Your JSON output is parsed and the aspect strings are rendered by KaTeX
inside a React frontend. A missing backslash on a LaTeX command renders as
literal text ("mathbbE" instead of 𝔼). A `page_to: "44"` string trips strict
schema validation and forces a json_object fallback that drops citations.
</context_addendum>

<task_addendum>
Follow EVERY rule below or formulas will not render:

1. Every standalone formula MUST be on its own line wrapped in $$ ... $$
   (display math). Inline math uses $...$ only inside a running sentence.
   NEVER leave a major formula inline.

2. Every LaTeX command starts with a backslash. In JSON strings, double the
   backslash so the rendered text contains a single one:
   - variance:  $$\\\\mathrm{Var}(X) = \\\\mathbb{E}\\\\left[(X-\\\\mathbb{E}[X])^2\\\\right]$$
   - MSE:       $$\\\\mathrm{MSE}(\\\\hat{\\\\theta}) = \\\\mathrm{Var}(\\\\hat{\\\\theta}) + \\\\mathrm{Bias}(\\\\hat{\\\\theta})^2$$
   - sigma:     \\\\sigma         (NOT sigma)
   - hat:       \\\\hat{\\\\theta}   (NOT hat{\\\\theta})
   - text:      \\\\text{Var}      (NOT text{Var})

3. Citations: every chunk you reference MUST appear in the `citations` array
   with a numeric inline marker `[N]`. Set `year` to an integer or null;
   `section` to a string (use "" if unknown); `page_from` and `page_to` MUST
   be integers, not strings.
</task_addendum>
"""


def _maybe_append_groq_addendum(system_prompt: str, model_id: str | None) -> str:
    """Append Groq-only formatting rules when the draft model is hosted on Groq."""
    from src.services.chat.llm.router import GROQ_MODEL_IDS  # noqa: PLC0415
    if model_id and model_id in GROQ_MODEL_IDS:
        return system_prompt + _GROQ_PROMPT_ADDENDUM
    return system_prompt


# Math-lift fallback: when the renderer's math_blocks list is empty but the
# answer text contains formula-like lines, lift the most prominent formulas
# into math_blocks so the UI's formula box still gets populated. Used as a
# safety net for providers (Groq) whose draft inlines all math.
_LIFT_LINE_RE = re.compile(r"(?m)^\s*\$\$\s*(.+?)\s*\$\$\s*$")
_LIFT_INLINE_FORMULA_RE = re.compile(
    r"\$([^$\n]{6,200}?(?:Var|MSE|Bias|mathbb|mathrm|sigma|hat|sum|frac)[^$\n]*?)\$"
)




_LATEX_POLISH_PROMPT = """\
<role>
You are a LATEX REPAIR TOOL — a deterministic, non-creative editor. You do not
rewrite, summarise, or rephrase; you only fix missing backslashes inside math
regions.
</role>

<context>
The input is ONE Markdown paragraph that may contain math regions delimited by
`$ ... $` (inline) or `$$ ... $$` (display). Some LaTeX commands inside these
regions are missing their leading backslash because an upstream Llama-class
model dropped it when serialising JSON. Examples: `mathbb{E}` should be
`\\mathbb{E}`, `sigma^2` should be `\\sigma^2`, `text{Var}` should be
`\\text{Var}`, `hat{\\theta}` should be `\\hat{\\theta}`, `frac{a}{b}` should
be `\\frac{a}{b}`. KaTeX otherwise renders them as literal text.
</context>

<task>
1. Find every bare LaTeX command inside math regions and add the missing
   backslash so KaTeX can render it.
2. Do NOT change anything outside `$...$` and `$$...$$` regions.
3. Do NOT add, remove, or rephrase formulas. Do NOT change variable names.
4. Preserve every newline, blank line, heading, citation marker `[N]`, and
   list bullet exactly as given.
</task>

<output>
ONLY the corrected paragraph as plain Markdown. No preamble, no explanation,
no JSON, no code fences.
</output>
"""


async def _polish_latex_via_llm(text: str, *, model: str | None = None) -> str:
    """Use a cheap, reliable LLM to repair missing backslashes in math regions.

    Used when the draft model (Groq Llama, gpt-oss, …) is known to drop
    backslashes when serialising LaTeX inside JSON strings. Best-effort:
    on any failure returns *text* unchanged so the answer still ships.

    Args:
        text: Aspect body (Markdown, may contain `$...$` and `$$...$$`).
        model: Override model (defaults to ``openai_model_nano`` — the
            structured-output-reliable path).

    Returns:
        Corrected text, or the original text on any error / empty input.
    """
    if not text or "$" not in text:
        return text
    polish_model = model or settings.openai_model_nano
    oa = _async_client(polish_model)
    try:
        resp = await oa.chat.completions.create(
            model=polish_model,
            messages=[
                {"role": "system", "content": _LATEX_POLISH_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.0,
            max_completion_tokens=max(800, min(_MAX_COMPLETION_TOKENS, len(text) // 2 + 400)),
        )
        out = (resp.choices[0].message.content or "").strip()
        # Guard: if the model returned empty or shorter than half the input,
        # assume it summarised rather than repaired — keep the original.
        if len(out) < max(40, len(text) // 2):
            return text
        return out
    except Exception:  # noqa: BLE001
        logger.exception("LaTeX polish stage failed; keeping original text")
        return text


def _lift_math_blocks_from_text(text: str, *, limit: int = 6) -> list[str]:
    """Extract candidate display-math strings from *text*.

    Used only when the model failed to emit `$$ ... $$` blocks. Returns a
    de-duplicated list of LaTeX strings wrapped in `$$...$$` so they match
    the schema produced by the OpenAI path.
    """
    seen: set[str] = set()
    out: list[str] = []
    for m in _LIFT_LINE_RE.finditer(text or ""):
        body = m.group(1).strip()
        if body and body not in seen:
            seen.add(body)
            out.append(f"$$ {body} $$")
            if len(out) >= limit:
                return out
    # Fallback: lift inline `$...$` formulas that contain LaTeX commands.
    for m in _LIFT_INLINE_FORMULA_RE.finditer(text or ""):
        body = m.group(1).strip()
        if body and body not in seen:
            seen.add(body)
            out.append(f"$$ {body} $$")
            if len(out) >= limit:
                break
    return out
# Draft creativity. The OpenAI structured draft path previously passed no
# temperature (model default ~1.0, uncontrolled); the deepseek/json fallbacks
# used 0.2. A single moderate knob balances factuality against the creativity
# needed to connect concepts across sources. Plan/extract/judge/coverage calls
# stay at 0.0 — they must be deterministic.
_DRAFT_TEMPERATURE = float(os.environ.get("TUTOR_DEEP_TEMPERATURE", "0.4"))
# Draft-model default — Phase 2: upgraded to the full OpenAI model for
# steadier latency and stronger articulation. Revert via:
#   TUTOR_DRAFT_MODEL=gpt-5.4-nano-2026-03-17
# The lazy evaluation (lambda) defers settings access until first use so
# config is fully loaded before the fallback is read.
_DRAFT_MODEL_DEFAULT: str = (
    os.environ.get("TUTOR_DRAFT_MODEL", "") or settings.openai_model_full
)


def _resolve_draft_default(req_model: str | None) -> str:
    """Base model for the draft stage.

    The request's ``model`` field carries a non-null schema default
    (``openai_model_nano``), so a bare request cannot be distinguished from an
    explicit nano pick by truthiness alone. Phase 2 routes the draft to the
    stronger ``_DRAFT_MODEL_DEFAULT`` (full OpenAI model) UNLESS the user
    explicitly picked a *different* model in the picker. An explicit non-nano
    ``req.model`` still wins (honors the About-model feature); the schema
    default and an empty value both fall through to the full draft default.
    To force nano draft, set ``TUTOR_DRAFT_MODEL`` or use
    ``stageModels["draft"]``.
    """
    if req_model and req_model != settings.openai_model_nano:
        return req_model
    return _DRAFT_MODEL_DEFAULT
_WIDE_POOL = int(os.environ.get("TUTOR_DEEP_POOL", "30"))
_IMAGES_ENABLED = os.environ.get("TUTOR_DEEP_IMAGES", "1") == "1"
# Vision-explain (#9): have a vision model read each placed figure and
# explain it in light of the concept just taught.
# Tri-state via TUTOR_DEEP_VISION_EXPLAIN:
#   "1"    -> explain only the single top-ranked figure.
#   "lazy" -> no inline vision call; figure renders with caption+judge_reason.
#   "0"    -> off (same as lazy for callers).
# DEFAULT "lazy" — saves 2-3 vision calls per turn with zero quality loss
# (placement code already falls back to caption+judge_reason).
_VISION_EXPLAIN_MODE: str = os.environ.get("TUTOR_DEEP_VISION_EXPLAIN", "lazy").lower()
# Legacy boolean shim retained so existing call sites that read _VISION_EXPLAIN
# still behave: True only when mode is explicitly "1".
_VISION_EXPLAIN: bool = _VISION_EXPLAIN_MODE == "1"

# ── Per-stage model overrides (About-model feature) ───────────────────────
# Only these LLM-text stages may be re-routed to a picker chat model. Other
# stages (retrieval/rerank use no chat LLM; vision needs a vision model;
# embedding needs an embedding model) are never overridden.
_OVERRIDABLE_STAGES = frozenset({"expansion", "draft", "critique", "image_judge"})


def _known_chat_models() -> set[str]:
    """Valid model ids from the picker registry (cached)."""
    global _KNOWN_CHAT_MODELS_CACHE
    try:
        return _KNOWN_CHAT_MODELS_CACHE
    except NameError:
        pass
    ids: set[str] = set()
    try:
        for p in list_providers():
            for m in p.models:
                ids.add(m.id)
    except Exception:  # noqa: BLE001
        logger.exception("could not load provider registry for validation")
    globals()["_KNOWN_CHAT_MODELS_CACHE"] = ids
    return ids


def _resolve_stage_model(stage: str, default_model: str, stage_models: dict | None) -> str:
    """Model id for *stage*. Honors a valid override; else the stage default.

    ``default_model`` is the draft default (``req.model``); non-draft stages
    default to the cheap nano unless explicitly overridden."""
    base = default_model if stage == "draft" else settings.openai_model_nano
    if stage not in _OVERRIDABLE_STAGES:
        return base
    cand = (stage_models or {}).get(stage)
    if cand and cand in _known_chat_models():
        return cand
    return base


# Vision-explain stage model. Unlike text stages, this defaults to a
# vision-capable model (gpt-4o-mini), not nano. A picker override is honored
# when it is a known chat model; a non-vision pick degrades gracefully because
# _explain_figure_vision falls back to the caption on any API error.
def _vision_default_model() -> str:
    return os.environ.get("TUTOR_DEEP_VISION_MODEL", "gpt-4o-mini")


def _resolve_vision_model(stage_models: dict | None) -> str:
    cand = (stage_models or {}).get("vision_explain")
    if cand and cand in _known_chat_models():
        return cand
    return _vision_default_model()


# Synthesis-plan stage (workflow A). One LLM call builds a thesis + evidence
# ledger + author contrasts before the draft. ON by default; the pipeline node's
# dropdown sends stageModels["plan"] = "off" to disable, or a model id to enable
# with that model.
_SYNTHESIS_PLAN_ON = os.environ.get("TUTOR_SYNTHESIS_PLAN", "1") == "1"


def _resolve_plan_model(stage_models: dict | None) -> tuple[bool, str]:
    """``(enabled, model)`` for the synthesis-plan stage.

    ``stageModels["plan"]``: ``"off"`` → disabled; a known chat model →
    enabled with it; absent/unknown → env default (on, nano).
    """
    cand = (stage_models or {}).get("plan")
    if isinstance(cand, str) and cand.strip().lower() == "off":
        return (False, "")
    if cand and cand in _known_chat_models():
        return (True, cand)
    return (_SYNTHESIS_PLAN_ON, settings.openai_model_nano)


# Drafting workflow (single draft vs orchestrator-workers vs long-context organize).
_WORKFLOW_DEFAULT = os.environ.get("TUTOR_WORKFLOW", "single")
_WORKER_MODEL = os.environ.get("TUTOR_WORKER_MODEL", "") or None  # None → nano
# Long-context organizer (§11): hand a large source pool to deepseek-v4-pro and
# let it organize the coherent pieces (formulas, the central decomposition/MSE,
# real cases) into the aspect fields. Token-budgeted; never assumes a 1M window.
_ORGANIZE_MODEL = os.environ.get("TUTOR_ORGANIZE_MODEL", "") or settings.deepseek_model
_ORGANIZE_MAX_TOKENS = int(os.environ.get("TUTOR_ORGANIZE_MAX_TOKENS", "120000"))
_ORGANIZE_POOL = int(os.environ.get("TUTOR_ORGANIZE_POOL", "60"))


def _resolve_workflow(req) -> str:
    """``"single"``, ``"orchestrator"``, or ``"organize"`` — request field over
    env default."""
    val = str(getattr(req, "tutorWorkflow", None) or _WORKFLOW_DEFAULT).lower()
    if val in ("orchestrator", "organize"):
        return val
    return "single"


_IMAGE_POOL = int(os.environ.get("TUTOR_DEEP_IMAGE_POOL", "6"))

# Author-perspective diversity (T-diversity).
# TUTOR_DIVERSITY=1  → diversity ON by default.
# TUTOR_DIVERSITY_MAX_AUTHORS → hard cap / "auto" ceiling on distinct authors.
# TUTOR_DIVERSITY_TARGET_AUTHORS → legacy fallback for the cap (kept for compat).
# When a request leaves diversityAuthors unset, the default mode is "auto":
# the concept-extraction model suggests the count, clamped to the cap and to
# however many authors actually exist in the candidate pool.
_DIVERSITY_ON = os.environ.get("TUTOR_DIVERSITY", "1") == "1"
_DIVERSITY_TARGET = int(os.environ.get("TUTOR_DIVERSITY_TARGET_AUTHORS", "3"))
_DIVERSITY_MAX = int(os.environ.get("TUTOR_DIVERSITY_MAX_AUTHORS", str(max(_DIVERSITY_TARGET, 6))))
# Default mode when the request omits diversityAuthors ("auto" | "off" | a fixed int as str).
_DIVERSITY_DEFAULT_MODE = os.environ.get("TUTOR_DIVERSITY_DEFAULT", "auto")


def _resolve_diversity(req_val: "int | str | None") -> tuple[str, int]:
    """Map the request's ``diversityAuthors`` to ``(mode, cap)``.

    mode: ``"off"`` (no diversification), ``"fixed"`` (hard cap = N), or
    ``"auto"`` (concept model suggests, clamped to cap). ``cap`` is the ceiling.
    """
    raw = req_val
    if raw is None:
        if not _DIVERSITY_ON:
            return ("off", 0)
        raw = _DIVERSITY_DEFAULT_MODE  # "auto" by default
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s == "auto":
            return ("auto", max(2, _DIVERSITY_MAX))
        if s in ("off", "", "0", "1"):
            return ("off", 0)
        try:
            raw = int(s)
        except ValueError:
            return ("auto", max(2, _DIVERSITY_MAX))
    n = int(raw)
    if n <= 1:
        return ("off", 0)
    return ("fixed", min(n, _DIVERSITY_MAX))
# Disable concurrent reranker pre-warm by default: sentence-transformers'
# meta-tensor initialisation racing with the first real predict() call has
# been observed to raise "Cannot copy out of meta tensor".  First request
# pays a ~5s cold-load tax instead.  Opt back in with TUTOR_DEEP_WARM=1.
_WARM_RERANKER_ON_IMPORT = os.environ.get("TUTOR_DEEP_WARM", "0") == "1"


# ---------------------------------------------------------------------------
# Reranker warm-up (avoid 5-8s cold load on first request)
# ---------------------------------------------------------------------------


def _warm_reranker_background() -> None:
    """Load the cross-encoder in a background thread."""
    import threading

    def _load() -> None:
        try:
            r = get_reranker()
            # Touch the cached_property to load the underlying CrossEncoder.
            model = r._model
            # Run a tiny predict to materialise any lazy weights.
            try:
                model.predict([("warm", "warm")], show_progress_bar=False)
            except Exception:  # noqa: BLE001
                logger.exception("deep_tutor: reranker predict-warm failed (model still loaded)")
            logger.info("deep_tutor: reranker warmed")
        except Exception:  # noqa: BLE001
            logger.exception("deep_tutor: reranker warm failed")

    threading.Thread(target=_load, daemon=True, name="deep-tutor-rerank-warm").start()


if _WARM_RERANKER_ON_IMPORT:
    _warm_reranker_background()


# ---------------------------------------------------------------------------
# OpenAI helpers
# ---------------------------------------------------------------------------


def _async_client(model_id: str | None = None) -> _openai.AsyncOpenAI:
    """Return AsyncOpenAI client routed to the provider hosting ``model_id``.

    Without a model_id, defaults to OpenAI (legacy behaviour for stages that
    have no per-stage override). With one, dispatches to Groq/DeepSeek
    base_url + key when applicable.
    """
    from src.services.chat.llm.router import aclient_for  # noqa: PLC0415
    return aclient_for(model_id)


# ---------------------------------------------------------------------------
# Concept extraction
# ---------------------------------------------------------------------------


async def extract_concepts(query: str, *, model: str | None = None) -> list[str]:
    """Run an LLM call to extract 1-3 technical concepts. *model* defaults to
    nano; an OpenAI override is honored, others degrade to the keyword
    heuristic via the except path."""
    if not query.strip():
        return []
    chosen_model = model or settings.openai_model_nano
    oa = _async_client(chosen_model)
    try:
        resp = await oa.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system", "content": EXTRACT_CONCEPTS_PROMPT},
                {"role": "user", "content": query},
            ],
            temperature=0.0,
            max_completion_tokens=120,
        )
        raw = strip_fences(resp.choices[0].message.content or "[]")
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return []
        return [str(x).strip() for x in parsed if str(x).strip()][:3]
    except Exception:  # noqa: BLE001
        logger.exception("extract_concepts failed; degrading to keyword heuristic")
        words = [
            w.strip(" ?!.,;:\"'()[]{}").lower()
            for w in query.split()
            if len(w) > 4
        ]
        seen: set[str] = set()
        out: list[str] = []
        for w in words:
            if w in seen:
                continue
            seen.add(w)
            out.append(w)
            if len(out) >= 3:
                break
        return out


class QueryPlan(NamedTuple):
    """Top-orchestrator output (one nano call): concepts + author budget +
    retrieval queries + the facets the answer must cover."""
    concepts: list[str]
    suggested_authors: int
    queries: list[str]
    facets: list[str]


async def extract_concepts_ex(
    query: str, *, model: str | None = None, max_authors: int = 4
) -> QueryPlan:
    """Query planner (top orchestrator) in ONE LLM call: concepts, the
    author-perspective budget, targeted retrieval ``queries`` and the
    ``facets`` the answer must cover. On any failure it falls back to the
    keyword-heuristic concepts, a neutral budget, and empty queries/facets
    (the caller then behaves like the legacy single-query path).
    """
    max_authors = max(1, int(max_authors))
    if not query.strip():
        return QueryPlan([], 1, [], [])
    chosen_model = model or settings.openai_model_nano
    oa = _async_client(chosen_model)
    try:
        resp = await oa.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system",
                 "content": EXTRACT_CONCEPTS_BUDGET_PROMPT.format(max_authors=max_authors)},
                {"role": "user", "content": query},
            ],
            temperature=0.0,
            max_completion_tokens=400,
        )
        raw = strip_fences(resp.choices[0].message.content or "{}")
        parsed = json.loads(raw)
        concepts = [str(x).strip() for x in (parsed.get("concepts") or []) if str(x).strip()][:3]
        n = int(parsed.get("perspectives", min(2, max_authors)))
        n = max(1, min(max_authors, n))
        queries = [str(x).strip() for x in (parsed.get("queries") or []) if str(x).strip()][:4]
        facets = [str(x).strip() for x in (parsed.get("facets") or []) if str(x).strip()][:6]
        return QueryPlan(concepts, n, queries, facets)
    except Exception:  # noqa: BLE001
        logger.exception("extract_concepts_ex failed; degrading to keyword heuristic + neutral budget")
        concepts = await extract_concepts(query, model=model)
        return QueryPlan(concepts, min(2, max_authors), [], [])


# ---------------------------------------------------------------------------
# Parallel retrieval — wide candidate pull (no rerank, no concept scoring)
# ---------------------------------------------------------------------------


async def _wide_candidates(
    query: str, book_slugs: list[str] | None, pool: int
) -> tuple[list[Source], RetrievalMetadata]:
    """Off-thread wide RRF pull. Runs in parallel with concept extraction."""
    return await asyncio.to_thread(
        hybrid_search,
        query,
        book_slugs=book_slugs,
        top_k=pool,
        rerank=False,
    )


def _rrf_merge(pools: list[list[Source]], *, k: int = 60) -> list[Source]:
    """Reciprocal-rank fusion of multiple ranked Source lists, keyed by
    ``chunkId``. Returns one deduped list ordered by fused score."""
    scores: dict[str, float] = {}
    best: dict[str, Source] = {}
    for pool in pools:
        for rank, src in enumerate(pool):
            cid = src.chunkId or f"{src.book}:{src.section}:{rank}"
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            if cid not in best:
                best[cid] = src
    ordered = sorted(best.values(), key=lambda s: scores[s.chunkId or ""], reverse=True)
    return ordered


# Multi-query retrieval (top-orchestrator query planner). ON by default.
_MULTI_QUERY = os.environ.get("TUTOR_MULTI_QUERY", "1") == "1"
# Concept-TF weight in section scoring (alpha in _section_score); higher =
# term frequency matters more vs the RRF score.
_DENSITY_ALPHA = float(os.environ.get("TUTOR_DENSITY_ALPHA", "0.6"))
# Adjacent-section (sibling) expansion, gated by the cross-encoder rerank.
_NEIGHBOR_EXPAND = os.environ.get("TUTOR_NEIGHBOR_EXPAND", "1") == "1"


async def _multi_query_candidates(
    queries: list[str], book_slugs: list[str] | None, pool: int
) -> list[Source]:
    """Run a wide pull per planned query in parallel and RRF-fuse the pools.
    Returns the fused candidate list (no rerank). Empty queries → []."""
    qs = [q for q in (queries or []) if q.strip()]
    if not qs:
        return []
    results = await asyncio.gather(
        *(_wide_candidates(q, book_slugs, pool) for q in qs),
        return_exceptions=True,
    )
    pools = [r[0] for r in results if not isinstance(r, BaseException)]
    return _rrf_merge(pools) if pools else []


def _apply_section_parent_diversity(
    sources: list[Source],
    ranked_all: list[Source],
    eff_top_n: int,
) -> list[Source]:
    """Secondary section-parent (chapter) diversity tiebreak.

    When all surviving *sources* share the same chapter/parent framing,
    reinsert the best dropped source (from *ranked_all[eff_top_n:]*) from a
    DIFFERENT chapter so at least one distinct framing survives the trim.

    - Author diversity is PRIMARY and was already applied before this call.
    - At most ONE extra source is added (avoid bloating the pool).
    - Degrades gracefully: if chapter metadata is absent on any source, the
      function returns *sources* unchanged.
    """
    # Collect distinct chapter keys in current selection (empty-string means
    # metadata absent — treat as unknown, skip diversity for that source).
    chapters_in = [s.chapter for s in sources if s.chapter]
    if not chapters_in:
        return sources  # no chapter metadata → degrade silently

    unique_chapters = set(chapters_in)
    if len(unique_chapters) > 1:
        return sources  # already diverse — nothing to do

    # All sources share a single chapter framing. Look for the best dropped
    # source from a different chapter in the ranked remainder.
    dropped = ranked_all[eff_top_n:]
    for s in dropped:
        if s.chapter and s.chapter not in unique_chapters:
            logger.debug(
                "_density_select: section-parent tiebreak re-inserted chapter=%s", s.chapter
            )
            return sources + [s]

    return sources  # no alternative framing in pool → degrade cleanly


def _density_select(
    query: str,
    concepts: list[str],
    candidates: list[Source],
    *,
    book_slugs: list[str] | None,
    top_sections: int,
    final_top_n: int,
    target_authors: int = 0,
) -> tuple[list[Source], list[str]]:
    """Score candidates by concept density, expand top sections, rerank.

    When ``target_authors >= 2`` the final section-key selection goes through
    :func:`~src.services.chat.retrievers.diversity.diversify_section_keys`
    (round-robin by author group, year-spread tiebreak).  A stratified fill
    step (plan B) then attempts to satisfy any remaining author gap using only
    the already-fetched candidate pool filtered to under-represented authors —
    no extra Qdrant round-trips needed in most cases (one targeted scroll per
    missing slot when the candidate pool is insufficient).

    Returns (sources, collections_hit).
    """
    if not candidates:
        return [], []

    effective_slugs = book_slugs or [b.id for b in list_books()]
    coll_map = collections_for_books(effective_slugs)
    collections_hit = list(coll_map.keys())

    if not concepts:
        # No concept signal — just take top candidates and rerank.
        ranked = get_reranker().rerank(query, candidates, top_n=final_top_n)
        return ranked, collections_hit

    # Aggregate by (book_slug, section_id) ------------------------------------
    from collections import defaultdict
    agg: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "max_score": 0.0, "authors_short": "", "authors": "", "book": "", "year": None}
    )
    max_count = 1
    max_score = 1e-9
    for src in candidates:
        text = src.chunk or src.excerpt or ""
        total = sum(_count_occurrences(text, c) for c in concepts)
        key = (src.book, src.section)
        bucket = agg[key]
        bucket["count"] += total
        bucket["max_score"] = max(bucket["max_score"], float(src.score))
        # Capture author/year from first encountered chunk for this section.
        if not bucket["authors"]:
            bucket["authors_short"] = src.authors_short or ""
            bucket["authors"] = src.authors or ""
            bucket["book"] = src.book or ""
            bucket["year"] = src.year
        if bucket["count"] > max_count:
            max_count = bucket["count"]
        if bucket["max_score"] > max_score:
            max_score = bucket["max_score"]

    scored: list[tuple[tuple[str, str], float]] = [
        (key, _section_score(b["count"] / max_count, b["max_score"] / max_score, alpha=_DENSITY_ALPHA))
        for key, b in agg.items()
    ]
    scored.sort(key=lambda t: t[1], reverse=True)
    with_hits = [t for t in scored if agg[t[0]]["count"] > 0]
    ranked_keys = [k for k, _ in (with_hits or scored)]

    # Build key_meta for the diversity pass -----------------------------------
    key_meta: dict[tuple[str, str], AuthorMeta] = {
        key: AuthorMeta(
            authors_short=agg[key]["authors_short"],
            authors=agg[key]["authors"],
            book=agg[key]["book"],
            year=agg[key]["year"],
            score=_section_score(
                agg[key]["count"] / max_count,
                agg[key]["max_score"] / max_score,
                alpha=_DENSITY_ALPHA,
            ),
        )
        for key in ranked_keys
    }

    # -- Plan A: round-robin diversity selection ------------------------------
    # Slot budget must scale with the author target: you need >= N sections to
    # surface N distinct authors (one author per section in the best case).
    eff_sections = max(top_sections, target_authors) if target_authors >= 2 else top_sections
    if target_authors >= 2:
        final_keys = diversify_section_keys(ranked_keys, key_meta, target_authors, eff_sections)
        logger.debug(
            "_density_select: diversity target=%d, eff_sections=%d, ranked=%d, selected=%d keys",
            target_authors, eff_sections, len(ranked_keys), len(final_keys),
        )
    else:
        final_keys = ranked_keys[:top_sections]

    # -- Plan B: stratified fill for under-represented authors ----------------
    diversity_fired = False
    if target_authors >= 2 and len(final_keys) < eff_sections:
        # Count distinct authors already in selection.
        picked_authors: set[str] = {
            author_key(key_meta[k]) for k in final_keys if k in key_meta
        }
        missing_slots = eff_sections - len(final_keys)
        # Filter candidate pool to under-represented authors.
        gap_candidates = build_author_filter_from_candidates(picked_authors, candidates)
        # Aggregate gap candidates by section, pick the best section per
        # new-author not already in final_keys.
        gap_agg: dict[tuple[str, str], dict[str, Any]] = defaultdict(
            lambda: {"max_score": 0.0, "authors_short": "", "authors": "", "book": "", "year": None}
        )
        final_key_set = set(final_keys)
        for src in gap_candidates:
            key = (src.book, src.section)
            if key in final_key_set:
                continue
            b = gap_agg[key]
            b["max_score"] = max(b["max_score"], float(src.score))
            if not b["authors"]:
                b["authors_short"] = src.authors_short or ""
                b["authors"] = src.authors or ""
                b["book"] = src.book or ""
                b["year"] = src.year
        if gap_agg:
            gap_scored = sorted(
                gap_agg.items(), key=lambda t: t[1]["max_score"], reverse=True
            )
            # Add best new-author sections up to missing_slots, capped at target_authors extra calls.
            added = 0
            for key, meta in gap_scored:
                if added >= min(missing_slots, target_authors):
                    break
                final_keys.append(key)
                added += 1
                diversity_fired = True
            if diversity_fired:
                logger.debug(
                    "_density_select: stratified fill added %d section(s) from "
                    "under-represented authors", added,
                )

    # Expand sections ---------------------------------------------------------
    seen_ids: set[str] = set()
    expanded_points: list[Any] = []
    for book_slug, section_id in final_keys:
        sec_pages = [
            src.page_from for src in candidates
            if src.book == book_slug and src.section == section_id and src.page_from is not None
        ]
        for src in candidates:
            if src.book == book_slug and src.section == section_id and src.chunkId not in seen_ids:
                seen_ids.add(src.chunkId)
                expanded_points.append(_source_to_pseudo_point(src))
        extra = _fetch_section_chunks(
            book_slug, section_id, collections_hit, seen_ids,
            max_per_section=_MAX_CHUNKS_PER_SECTION,
        )
        expanded_points.extend(extra)
        # Adjacent-section (sibling) expansion — rerank below is the gate.
        if _NEIGHBOR_EXPAND and sec_pages:
            expanded_points.extend(_fetch_neighbor_chunks(
                book_slug, section_id, min(sec_pages), collections_hit, seen_ids,
            ))

    pre_rerank = [_point_to_source(p, rank=i + 1) for i, p in enumerate(expanded_points)]
    sources = pre_rerank
    if pre_rerank:
        # Diversity must not be starved by the relevance trim: widen the cut to
        # the author target, then guarantee >=1 surviving chunk per picked author.
        eff_top_n = max(final_top_n, target_authors) if target_authors >= 2 else final_top_n
        ranked_all = get_reranker().rerank(query, pre_rerank, top_n=len(pre_rerank))
        sources = ranked_all[:eff_top_n]
        if target_authors >= 2:
            kept = {author_key(s) for s in sources}
            # Author floor: if the relevance trim left FEWER distinct authors than
            # the target, top up toward the target with the best dropped chunk of
            # each missing author. Budget = remaining slots so we never overshoot
            # the target (which is a ceiling in fixed mode).
            budget = target_authors - len(kept)
            reinserts: list[Source] = []
            seen_auth: set[str] = set()
            for s in (ranked_all[eff_top_n:] if budget > 0 else []):
                ak = author_key(s)
                if ak and ak not in kept and ak not in seen_auth:
                    reinserts.append(s)
                    seen_auth.add(ak)
                if len(reinserts) >= budget:
                    break
            if reinserts:
                sources = sources + reinserts
                logger.debug("_density_select: rerank floor re-inserted %d author(s)", len(reinserts))

        # Secondary tiebreak: section-parent (chapter) diversity.
        # When all surviving sources share the same chapter/parent framing,
        # reinsert the best dropped source from a DIFFERENT chapter so at least
        # one distinct framing survives the trim.  Author-diversity is primary
        # (already applied above); this pass adds one slot only when needed and
        # degrades gracefully if section metadata (chapter) is absent.
        sources = _apply_section_parent_diversity(sources, ranked_all, eff_top_n)

    # Log diversity outcome for observability.
    if target_authors >= 2:
        distinct_authors = len({author_key(s) for s in sources if s.authors or s.book})
        logger.info(
            "_density_select: diversity target=%d, distinct_authors_in_result=%d, "
            "stratified_fill=%s",
            target_authors, distinct_authors, diversity_fired,
        )

    return sources, collections_hit


# ---------------------------------------------------------------------------
# Draft — single LLM call with streaming + DeepTutorAnswer parse
# ---------------------------------------------------------------------------


def _format_figure_bundle(figures: list) -> str:
    """Render approved figures so the LLM can place ``[F<i>]`` markers."""
    if not figures:
        return "<figures>(none)</figures>"
    parts: list[str] = ["<figures>"]
    for i, f in enumerate(figures, 1):
        parts.append(
            f"<figure marker='F{i}' aspect='{f.aspect_hint or 'example_intuition'}' "
            f"role='{f.figure_role or 'other'}'>\n"
            f"  ref: {f.ref} | book: {f.book} | chapter: {f.chapter}\n"
            f"  caption: {(f.caption or '')[:300]}\n"
            f"</figure>"
        )
    parts.append("</figures>")
    parts.append(
        "Insert each figure's marker ``[F<i>]`` exactly once inside the "
        "aspect named in its ``aspect`` attribute (e.g. [F1] in the "
        "``example_intuition`` field).  Do not invent new markers.  Skip figures "
        "that do not naturally fit the surrounding prose."
    )
    return "\n".join(parts)


def _format_plan_block(plan: SynthesisPlan | None) -> str:
    """Render a SynthesisPlan as <synthesis_plan>/<contrasts> blocks for the
    draft user message. Empty string when no usable plan."""
    if plan is None or not (plan.thesis or plan.contrasts or plan.tasks):
        return ""
    parts: list[str] = ["<synthesis_plan>"]
    if plan.thesis:
        parts.append(f"thesis: {plan.thesis}")
    for t in (plan.tasks or []):
        if t.focus:
            parts.append(f"- angle: {t.focus}")
    parts.append("</synthesis_plan>")
    if plan.contrasts:
        parts.append("<contrasts>")
        for ct in plan.contrasts:
            parts.append(
                f"- {ct.topic}: {ct.author_a} — {ct.position_a} || "
                f"{ct.author_b} — {ct.position_b}"
            )
        parts.append("</contrasts>")
    return "\n".join(parts)


def _build_user_message(
    query: str, sources: list[Source], figures: list | None = None,
    plan: SynthesisPlan | None = None,
) -> str:
    bundle = format_source_bundle(sources)
    fig_bundle = _format_figure_bundle(figures or [])
    plan_block = _format_plan_block(plan)
    plan_part = f"{plan_block}\n\n" if plan_block else ""
    return (
        f"<question>\n{query}\n</question>\n\n"
        f"{bundle}\n\n"
        f"{plan_part}"
        f"{fig_bundle}\n\n"
        f"Write the answer now. Fill every field of the DeepTutorAnswer schema "
        f"with substantive content per the length guidance in the system prompt."
    )


async def build_synthesis_plan(
    query: str, sources: list[Source], *, model: str | None = None
) -> SynthesisPlan | None:
    """One structured call → a thesis + per-aspect outline + author-tagged
    evidence ledger + explicit author contrasts. Best-effort: returns ``None``
    on any failure (caller proceeds with the plain single-draft path).

    Routing: model IDs starting with ``"deepseek"`` go through the provider
    router with ``response_format={"type": "json_object"}`` and are parsed
    into :class:`SynthesisPlan` manually (DeepSeek does not support OpenAI's
    Pydantic ``parse()`` helper). Everything else uses OpenAI's native
    structured-output ``parse()`` path.
    """
    if not sources:
        return None
    user = (
        f"<question>\n{query}\n</question>\n\n{format_source_bundle(sources)}\n\n"
        f"Return the synthesis plan JSON now."
    )
    model_id = model or settings.openai_model_nano
    try:
        if model_id.startswith("deepseek"):
            # DeepSeek path — stream JSON via router, parse into SynthesisPlan.
            client, resolved = get_llm(model_id)
            chat_msgs = [
                ChatMessage(role="system", content=SYNTHESIS_PLAN_PROMPT),
                ChatMessage(role="user", content=user),
            ]
            # Reasoner emits long chain-of-thought; tight 1200-cap truncates
            # the JSON mid-string and json.loads fails. Give 8000 to leave
            # headroom for the answer. (DeepSeek client ignores response_format.)
            buf: list[str] = []
            async for delta in client.stream(
                chat_msgs,
                model=resolved,
                temperature=0.0,
                max_tokens=8000,
                response_format={"type": "json_object"},
            ):
                if delta:
                    buf.append(delta)
            raw = strip_fences("".join(buf) or "{}")
            payload = _loads_tolerant_json_object(raw)
            if payload is None:
                logger.warning(
                    "build_synthesis_plan: deepseek returned unparseable JSON; "
                    "first 400 chars: %r", raw[:400]
                )
                return None
            return SynthesisPlan(**payload)
        else:
            # OpenAI path — native Pydantic structured output.
            oa = _async_client(model_id)
            resp = await oa.chat.completions.parse(
                model=model_id,
                messages=[
                    {"role": "system", "content": SYNTHESIS_PLAN_PROMPT},
                    {"role": "user", "content": user},
                ],
                response_format=SynthesisPlan,
                temperature=0.0,
                max_completion_tokens=1200,
            )
            return resp.choices[0].message.parsed
    except Exception:  # noqa: BLE001
        logger.exception("build_synthesis_plan failed; proceeding without a plan")
        return None


async def _stream_draft_via_router(
    model: str,
    messages: list[dict],
    accumulated: dict[str, str],
    on_aspect_delta,
) -> tuple[DeepTutorAnswer | None, dict[str, str]]:
    """Best-effort draft for non-OpenAI providers (deepseek, …): stream raw
    text via the provider router in JSON mode, forward deltas, then parse the
    full payload into :class:`DeepTutorAnswer`. Returns (None, accumulated)
    if the provider fails or emits unparseable JSON."""
    client, model_id = get_llm(model)
    chat_msgs = [ChatMessage(role=m["role"], content=m["content"]) for m in messages]
    buf: list[str] = []
    try:
        async for delta in client.stream(
            chat_msgs,
            model=model_id,
            temperature=_DRAFT_TEMPERATURE,
            max_tokens=_cap_max_tokens(model_id),
            response_format={"type": "json_object"},
        ):
            if not delta:
                continue
            buf.append(delta)
            if on_aspect_delta:
                on_aspect_delta("_raw", delta)
        raw = _repair_latex_escapes(strip_fences("".join(buf) or "{}"))
        # Truncation / chatty providers (esp. deepseek) often return prose
        # around the JSON or a JSON cut mid-string. Use the tolerant parser
        # so a near-complete payload still salvages instead of crashing.
        payload = _loads_tolerant_json_object(raw)
        if payload is None:
            logger.warning(
                "router draft (%s): unparseable JSON; first 400 chars: %r",
                model, raw[:400],
            )
            return None, accumulated
        # Empty / unusable payload (e.g. the provider streamed nothing) → let
        # the caller fall back rather than emit a blank answer. A PARTIAL
        # payload (some aspect keys) is salvaged: fill the missing aspect
        # fields with "" so a near-complete response is still usable instead
        # of failing strict construction.
        if not (set(payload) & set(ASPECT_HEADINGS)):
            return None, accumulated
        for key in ASPECT_HEADINGS:
            payload.setdefault(key, "")
        parsed_obj = DeepTutorAnswer(**payload)
        for key in ASPECT_HEADINGS:
            accumulated[key] = str(getattr(parsed_obj, key, "") or "")
        return parsed_obj, accumulated
    except Exception:  # noqa: BLE001
        logger.exception("router draft (%s) failed", model)
        return None, accumulated


async def _stream_draft(
    query: str,
    sources: list[Source],
    *,
    figures: list | None = None,
    on_aspect_delta=None,
    model: str | None = None,
    plan: SynthesisPlan | None = None,
    instructions: str | None = None,
) -> tuple[DeepTutorAnswer | None, dict[str, str]]:
    """Stream a draft and return (parsed answer, accumulated_aspects).

    ``on_aspect_delta(aspect_key, delta_text)`` is invoked for each new
    token chunk so the SSE layer can emit ``token`` events as they
    arrive.  When the structured-output stream API is unavailable we
    fall back to a non-streamed parse and emit the aspects as one
    final block.

    *model* selects the draft model. OpenAI-family models use the rich
    structured-streaming path below; non-OpenAI models (e.g. deepseek) use
    a best-effort text-stream + JSON-parse path via the provider router.
    """
    draft_model = model or settings.openai_model_nano
    user = _build_user_message(query, sources, figures=figures, plan=plan)
    sys_prompt = instructions or DEEP_TUTOR_INSTRUCTIONS
    sys_prompt = _maybe_append_groq_addendum(sys_prompt, draft_model)
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user},
    ]
    # Non-OpenAI providers (deepseek, …) — best-effort text-stream + JSON parse.
    if draft_model.startswith("deepseek"):
        return await _stream_draft_via_router(
            draft_model, messages, {k: "" for k in ASPECT_HEADINGS}, on_aspect_delta
        )
    return await _stream_structured(messages, draft_model, on_aspect_delta)


def _build_organize_pool(
    query: str, candidates: list[Source], ranked: list[Source], max_tokens: int
) -> list[Source]:
    """Build the large source pool the long-context organizer reads (§11).

    Reranks the wide candidate pool to ``_ORGANIZE_POOL``, guarantees the
    density-ranked ``ranked`` sources (the ones figures co-locate with) are
    included, then trims to a ``max_tokens`` budget (≈ ``chars/4``) so we never
    blow past the model's real context window. Token budget is approximate and
    deliberately conservative; the actual char/token total is logged by the
    caller. Best-effort: on any rerank error, falls back to ``ranked``."""
    try:
        wide = get_reranker().rerank(query, candidates, top_n=_ORGANIZE_POOL)
    except Exception:  # noqa: BLE001
        logger.exception("organize: rerank failed; using density-ranked sources only")
        wide = list(ranked)
    # Density-ranked sources first (highest-trust, figure-aligned), then the
    # rest of the wide pool, de-duplicated on chunkId.
    seen: set[str] = set()
    ordered: list[Source] = []
    for src in list(ranked) + wide:
        cid = src.chunkId or id(src)
        if cid in seen:
            continue
        seen.add(cid)
        ordered.append(src)
    out: list[Source] = []
    budget = 0
    for src in ordered:
        approx = len((src.chunk or src.excerpt or "")) // 4
        if out and budget + approx > max_tokens:
            break
        out.append(src)
        budget += approx
    return out


async def _stream_structured(
    messages: list[dict],
    model: str,
    on_aspect_delta=None,
) -> tuple[DeepTutorAnswer | None, dict[str, str]]:
    """Stream a ``DeepTutorAnswer`` from *messages* via the OpenAI structured
    streaming API, with ``parse()`` and raw-``json_object`` fallbacks. Shared by
    the single-draft path and the orchestrator's synthesizer pass. Invokes
    ``on_aspect_delta('_raw', delta)`` for each content delta so the SSE layer
    streams tokens as they arrive."""
    accumulated: dict[str, str] = {k: "" for k in ASPECT_HEADINGS}
    draft_model = model
    oa = _async_client(draft_model)

    # First try the structured streaming API. Falls back to non-stream
    # parse() on any error.
    try:
        async with oa.beta.chat.completions.stream(
            model=draft_model,
            messages=messages,
            response_format=DeepTutorAnswer,
            temperature=_DRAFT_TEMPERATURE,
            max_completion_tokens=_cap_max_tokens(draft_model),
        ) as stream:
            content_emitted = 0
            async for event in stream:
                etype = getattr(event, "type", "")
                if etype == "content.delta":
                    # Raw character-level delta from the JSON stream. Forwards
                    # immediately to the UI so TTFB is dominated by network
                    # rather than by JSON parsing of complete fields.
                    delta_text = getattr(event, "delta", "") or ""
                    if delta_text and on_aspect_delta:
                        on_aspect_delta("_raw", delta_text)
                        content_emitted += len(delta_text)
                    continue
                if etype != "chunk":
                    continue
                snap = getattr(event, "snapshot", None)
                parsed_dict: dict | None = None
                if snap is not None and hasattr(snap, "choices") and snap.choices:
                    msg = snap.choices[0].message
                    p = getattr(msg, "parsed", None)
                    if isinstance(p, dict):
                        parsed_dict = p
                    elif hasattr(p, "model_dump"):
                        try:
                            parsed_dict = p.model_dump()
                        except Exception:  # noqa: BLE001
                            parsed_dict = None
                if not parsed_dict:
                    continue
                for key in ASPECT_HEADINGS:
                    new_val = str(parsed_dict.get(key) or "")
                    if new_val and new_val != accumulated[key]:
                        accumulated[key] = new_val
            final = await stream.get_final_completion()
            parsed_obj = final.choices[0].message.parsed
            return parsed_obj, accumulated
    except (AttributeError, TypeError) as exc:
        logger.info("structured stream API unavailable (%s); falling back", exc)
    except Exception:  # noqa: BLE001
        logger.exception("structured stream failed; falling back to parse()")

    # Non-streaming fallback ------------------------------------------------
    try:
        resp = await oa.beta.chat.completions.parse(
            model=draft_model,
            messages=messages,
            response_format=DeepTutorAnswer,
            max_completion_tokens=_cap_max_tokens(draft_model),
        )
        parsed_obj = resp.choices[0].message.parsed
        if parsed_obj is not None:
            for key in ASPECT_HEADINGS:
                accumulated[key] = str(getattr(parsed_obj, key, "") or "")
        return parsed_obj, accumulated
    except Exception:  # noqa: BLE001
        logger.exception("parse() also failed; trying raw json_object")

    # Last-resort: raw JSON ------------------------------------------------
    try:
        resp = await oa.chat.completions.create(
            model=draft_model,
            messages=messages,
            temperature=_DRAFT_TEMPERATURE,
            response_format={"type": "json_object"},
            max_completion_tokens=_cap_max_tokens(draft_model),
        )
        raw = strip_fences(resp.choices[0].message.content or "{}")
        raw = _repair_latex_escapes(raw)
        payload = json.loads(raw)
        # Empty / unusable payload (e.g. the provider streamed nothing) → let
        # the caller fall back rather than emit a blank answer. A PARTIAL
        # payload (some aspect keys) is salvaged: fill the missing aspect
        # fields with "" so a near-complete response is still usable instead
        # of failing strict construction.
        if not isinstance(payload, dict) or not (set(payload) & set(ASPECT_HEADINGS)):
            return None, accumulated
        for key in ASPECT_HEADINGS:
            payload.setdefault(key, "")
        parsed_obj = DeepTutorAnswer(**payload)
        for key in ASPECT_HEADINGS:
            accumulated[key] = str(getattr(parsed_obj, key, "") or "")
        return parsed_obj, accumulated
    except Exception:  # noqa: BLE001
        logger.exception("all draft paths failed")
        return None, accumulated


# ---------------------------------------------------------------------------
# Critique (off by default — gated by TUTOR_DEEP_CRITIQUE)
# ---------------------------------------------------------------------------


async def critique(
    draft_text: str, concepts: list[str], sources: list[Source],
    *, model: str | None = None,
) -> dict[str, Any]:
    if not draft_text:
        return {"complete": False, "missing": concepts, "copy_paste_risk": "low",
                "reason": "empty draft"}
    src_summary = ", ".join(f"#{s.rank} {s.book} §{s.section}" for s in sources[:8])
    user = (
        f"<concepts>{json.dumps(concepts)}</concepts>\n"
        f"<sources>{src_summary}</sources>\n"
        f"<draft>\n{draft_text}\n</draft>"
    )
    # critique uses native JSON mode; deepseek override degrades to nano (OpenAI
    # path); Groq supports json_object natively so we keep the Groq model id.
    if model and (model.startswith("deepseek")):
        crit_model = settings.openai_model_nano
    else:
        crit_model = model or settings.openai_model_nano
    oa = _async_client(crit_model)
    try:
        resp = await oa.chat.completions.create(
            model=crit_model,
            messages=[
                {"role": "system", "content": CRITIQUE_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_completion_tokens=300,
            response_format={"type": "json_object"},
        )
        raw = strip_fences(resp.choices[0].message.content or "{}")
        data = json.loads(raw)
        return {
            "complete": bool(data.get("complete", True)),
            "missing": [str(m) for m in (data.get("missing") or [])][:3],
            "copy_paste_risk": str(data.get("copy_paste_risk", "low")),
            "reason": str(data.get("reason", ""))[:200],
        }
    except Exception:  # noqa: BLE001
        logger.exception("critique failed; defaulting to complete=True")
        return {"complete": True, "missing": [], "copy_paste_risk": "low",
                "reason": "critique error"}


# ---------------------------------------------------------------------------
# Conversion + helpers
# ---------------------------------------------------------------------------


def _sources_to_payload(sources: list[Source]) -> list[dict]:
    return [
        {
            "rank": s.rank, "book": s.book, "book_name": s.book_name or s.book,
            "authors": s.authors, "authors_short": s.authors_short, "year": s.year,
            "chapter": s.chapter, "section": s.section, "title": s.title,
            "page_from": s.page_from, "page_to": s.page_to, "page": s.page,
            "excerpt": s.excerpt, "chunk": (s.chunk or "")[:1500],
            "score": round(float(s.score), 4), "chunkId": s.chunkId,
        }
        for s in sources
    ]


def _merge_sources(a: list[Source], b: list[Source]) -> list[Source]:
    seen: set[str] = set()
    out: list[Source] = []
    for src in (*a, *b):
        if src.chunkId in seen:
            continue
        seen.add(src.chunkId)
        out.append(src)
    for i, src in enumerate(out, 1):
        src.rank = i
    return out


_VISION_EXPLAIN_PROMPT = (
    "<role>\n"
    "You are a statistics / ML tutor helping a learner understand a concept "
    "by reading the figure that accompanies it. You are not a caption "
    "rewriter — you must connect the visible pattern to the concept.\n"
    "</role>\n\n"
    "<context>\n"
    "The learner just read this material:\n"
    "<concept>\n{concept}\n</concept>\n"
    "You will be shown ONE figure (image_url) attached to this message. Your "
    "output is inlined next to the figure in the tutor answer, so the reader "
    "sees the figure first, then your 2-4 sentences.\n"
    "</context>\n\n"
    "<task>\n"
    "Write 2-4 sentences that:\n"
    "1. Describe what the figure SHOWS — name the axes or dimensions, the "
    "curves, bars, or regions you can actually see, and any visible trend or "
    "pattern (e.g. 'The x-axis is model complexity, the y-axis is prediction "
    "error. The U-shaped test-error curve bottoms out in the middle range.').\n"
    "2. Explain how that visual pattern directly illustrates the concept "
    "above (connect the picture to the idea, not just to its caption).\n"
    "</task>\n\n"
    "<rules>\n"
    "- Ground every claim in what is visible. Do NOT invent axis labels, tick "
    "values, or numbers you cannot read.\n"
    "- Do NOT paraphrase the caption verbatim.\n"
    "- If the figure is unreadable or unrelated to the concept, write one "
    "sentence saying so and stop.\n"
    "</rules>\n\n"
    "<output>\n"
    "Plain prose, 2-4 sentences. No JSON, no markdown headings.\n"
    "</output>"
)


async def _explain_figure_vision(concept_text: str, fig, model: str | None = None) -> str | None:
    """Vision-read one figure and explain it against *concept_text*.
    *model* selects the vision model (defaults to the configured vision model).
    Best-effort: returns None on any failure (caller falls back to caption)."""
    image_ref = resolve_image_for_vision(getattr(fig, "url", "") or "")
    if not image_ref:
        return None
    user_content = [
        {"type": "text", "text": _VISION_EXPLAIN_PROMPT.format(concept=concept_text[:1200])},
        {"type": "image_url", "image_url": {"url": image_ref}},
    ]
    try:
        oa = _async_client()
        resp = await oa.chat.completions.create(
            model=model or _vision_default_model(),
            messages=[{"role": "user", "content": user_content}],
            temperature=0.2,
            max_completion_tokens=220,
        )
        return (resp.choices[0].message.content or "").strip() or None
    except Exception:  # noqa: BLE001
        logger.exception("vision-explain failed; falling back to caption")
        return None


async def build_vision_explanations(
    aspects: dict[str, str], figures: list | None, model: str | None = None
) -> dict[str, str]:
    """Map figure ``url`` -> vision-generated explanation grounded in the
    definition + formal statement + intuition.

    Tri-state ``TUTOR_DEEP_VISION_EXPLAIN``:
    - ``"1"``    → explain only the single top-ranked figure (``figures[:1]``).
    - ``"lazy"`` → return ``{}``; placement code falls back to caption+judge_reason.
    - ``"0"``    → return ``{}``.
    """
    if _VISION_EXPLAIN_MODE not in ("1",) or not figures:
        return {}
    # Cap to the single top-ranked figure when mode == "1".
    figures_to_explain = figures[:1]
    concept = "\n\n".join(
        (aspects.get(k) or "") for k in ("definition", "formal_statement")
    ).strip()
    if not concept:
        return {}
    urls: list[str] = []
    tasks = []
    for f in figures_to_explain:
        url = getattr(f, "url", "") or ""
        if url:
            urls.append(url)
            tasks.append(_explain_figure_vision(concept, f, model=model))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out: dict[str, str] = {}
    for url, res in zip(urls, results):
        if isinstance(res, str) and res:
            out[url] = res
    return out


def _convert_to_tutor_answer(
    deep: DeepTutorAnswer | None,
    aspects: dict[str, str],
    sources: list[Source],
    approved_figures: list | None = None,
    vision_explanations: dict[str, str] | None = None,
    example_relevance_override: float | None = None,
) -> TutorAnswer:
    """Convert DeepTutorAnswer + aspect dict to a TutorAnswer payload.

    *approved_figures* (list of :class:`FigureRef`) comes from the image
    judge; we trust the judge over whatever the LLM may have emitted in
    ``deep.figures`` so the schema never contains hallucinated images.
    """
    if deep is None and not any(aspects.values()):
        return TutorAnswer(
            text="## Error\nFailed to generate an answer.",
            sections=["Error"], citations=[], aspects={},
        )
    final_aspects = {k: (getattr(deep, k, None) or aspects.get(k, "") or "") for k in ASPECT_HEADINGS}
    for k, v in final_aspects.items():
        repaired = _repair_latex_post(v)
        final_aspects[k] = _wrap_bare_math(repaired)

    figs_for_text = list(approved_figures) if approved_figures else (
        list(deep.figures) if deep else []
    )
    if figs_for_text:
        fallback = "example_intuition" if "example_intuition" in ASPECT_HEADINGS else next(iter(ASPECT_HEADINGS))
        # Score-based placement: pick the aspect with highest token overlap
        # between figure (caption + judge_reason) and aspect body. Falls
        # back to the judge-provided aspect_hint and finally to *fallback*.
        per_target: dict[str, list] = {}
        for f in figs_for_text:
            url = getattr(f, "url", "") or ""
            if not url:
                continue
            target = _choose_target_aspect(f, final_aspects, fallback)
            per_target.setdefault(target, []).append(f)
        fig_seq = 0
        for target, figs in per_target.items():
            base = final_aspects.get(target, "").rstrip()
            blocks: list[str] = []
            for f in figs:
                fig_seq += 1
                url = getattr(f, "url", "")
                book = getattr(f, "book", "") or "source"
                chapter = getattr(f, "chapter", "") or ""
                role = getattr(f, "figure_role", None) or "figure"
                cap_raw = (getattr(f, "caption", "") or "").replace("\n", " ").strip()
                reason = (getattr(f, "judge_reason", "") or "").replace("\n", " ").strip()
                label = f"{book} {chapter}".strip() or book
                topic = cap_raw.split(".")[0].strip() if cap_raw else "the concept above"
                lead = _build_lead(role, label, topic, fig_seq - 1)
                cap_alt = cap_raw or f"Figure from {book}"
                vis = (vision_explanations or {}).get(url, "").strip()
                if vis:
                    # #9: model has actually looked at the image and tied it
                    # to the concept just taught. Prefer it; keep caption as
                    # the alt text only.
                    explanation = vis
                else:
                    explain_parts: list[str] = []
                    if cap_raw:
                        explain_parts.append(cap_raw if cap_raw.endswith(".") else cap_raw + ".")
                    if reason and reason.lower() not in (cap_raw or "").lower():
                        explain_parts.append(reason if reason.endswith(".") else reason + ".")
                    if not explain_parts:
                        explain_parts.append(
                            f"This {role} is referenced as [F{fig_seq}] in the discussion above."
                        )
                    explanation = " ".join(explain_parts)
                blocks.append(f"### Figure example\n\n{lead}\n\n![{cap_alt}]({url})\n\n{explanation}")
            if blocks:
                final_aspects[target] = (base + "\n\n" + "\n\n".join(blocks)).strip()

    text = assemble_markdown(final_aspects)
    headings = [ASPECT_HEADINGS[k] for k in ASPECT_HEADINGS if final_aspects[k].strip()]

    raw_cites = list(deep.citations) if deep else []
    enriched = _reconcile_citations(raw_cites, sources)
    # Guarantee every inline [N] marker in the rendered text has a matching
    # citation entry, so the frontend pill always links to the sources panel.
    # Models (esp. via the deepseek router) sometimes emit markers without a
    # corresponding citations entry; synthesize the missing ones from sources
    # in marker order.
    enriched = _ensure_marker_citations(text, enriched, sources)

    math_blocks = list(deep.math_blocks) if deep else []
    if not math_blocks:
        # Math-lift fallback: providers that emit only inline math (Groq Llama,
        # gpt-oss) leave math_blocks empty. Lift candidate display formulas
        # from the joined aspect text so the formula box still renders.
        joined = "\n".join(str(final_aspects.get(k, "")) for k in ASPECT_HEADINGS)
        lifted = _lift_math_blocks_from_text(joined)
        if lifted:
            logger.info("math-lift fallback: extracted %d block(s) from inline text", len(lifted))
            math_blocks = lifted
    figures = list(approved_figures) if approved_figures else (
        list(deep.figures) if deep else []
    )
    # #8: prefer the embedding score (computed async upstream); fall back
    # to the cheap lexical overlap when it is unavailable.
    lexical_rel = _score_example_relevance(final_aspects)
    example_relevance = (
        example_relevance_override if example_relevance_override is not None else lexical_rel
    )
    if final_aspects.get("example_intuition", "").strip() and example_relevance < 0.15:
        logger.info(
            "deep-tutor: low example relevance %.3f — example may not "
            "illustrate the defined concept", example_relevance,
        )
    quality: dict[str, float] = {"example_relevance": example_relevance}
    # #7: audit a claimed-verbatim formal statement against the sources.
    verbatim = _verbatim_blockquote_match(final_aspects.get("formal_statement", ""), sources)
    if verbatim is not None:
        quality["formal_verbatim_match"] = verbatim
        if verbatim < 0.85:
            logger.info(
                "deep-tutor: formal-statement blockquote weak match %.3f — "
                "may not be truly verbatim from a source", verbatim,
            )
    return TutorAnswer(
        text=text, sections=headings, citations=enriched,
        math_blocks=math_blocks, figures=figures, aspects=final_aspects,
        quality=quality,
    )


def _ensure_marker_citations(
    text: str, enriched: list[TutorCitation], sources: list[Source]
) -> list[TutorCitation]:
    """Every inline ``[N]`` marker in *text* must have a citation entry whose
    ``index == N`` — otherwise the frontend pill has nothing to link to. For
    any marker missing from *enriched*, synthesize an entry from *sources*
    (by marker appearance order, then clamped to the last source)."""
    markers: list[int] = []
    for m in re.findall(r"\[(\d+)\]", text):
        n = int(m)
        if n not in markers:
            markers.append(n)
    if not markers or not sources:
        return enriched
    have = {c.index for c in enriched}
    out = list(enriched)
    for pos, n in enumerate(markers):
        if n in have:
            continue
        src = sources[min(pos, len(sources) - 1)]
        out.append(TutorCitation(
            index=n,
            chunkId=src.chunkId,
            authors_short=src.authors_short,
            year=src.year,
            book_name=src.book_name or src.book,
            chapter=src.chapter,
            section=src.section,
            page_from=src.page_from,
            page_to=src.page_to,
            quote=(src.excerpt or "")[:200],
        ))
    out.sort(key=lambda c: c.index)
    return out


def _reconcile_citations(
    cites: list[TutorCitation], sources: list[Source]
) -> list[TutorCitation]:
    by_chunk = {s.chunkId: s for s in sources}
    by_rank = {s.rank: s for s in sources}
    out: list[TutorCitation] = []
    for c in cites:
        src = by_chunk.get(c.chunkId) or by_rank.get(c.index)
        if src is None and sources:
            src = sources[0]
        if src is None:
            out.append(c)
            continue
        out.append(TutorCitation(
            index=c.index,
            chunkId=c.chunkId or src.chunkId,
            authors_short=c.authors_short or src.authors_short,
            year=c.year if c.year is not None else src.year,
            book_name=c.book_name or src.book_name or src.book,
            chapter=c.chapter or src.chapter,
            section=c.section or src.section,
            page_from=c.page_from if c.page_from is not None else src.page_from,
            page_to=c.page_to if c.page_to is not None else src.page_to,
            quote=c.quote,
        ))
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_deep_tutor(req: ChatRequest) -> AsyncIterator[dict]:
    """Execute the v2 deep-tutor pipeline and yield SSE event dicts."""
    t0 = time.time()
    timings: dict[str, int] = {}
    query = req.message or ""
    bf = getattr(req, "bookFilter", None)
    if isinstance(bf, list) and bf:
        book_slugs: list[str] | None = list(bf)
    else:
        book_slugs = None  # "ALL" / None / empty -> search all books

    pool = _WIDE_POOL

    # Per-stage model resolution (About-model feature). draft defaults to the
    # picker model; when no picker model is set, draft defaults to
    # _DRAFT_MODEL_DEFAULT (full OpenAI model, Phase 2 upgrade; revertible
    # via TUTOR_DRAFT_MODEL env). expansion/critique/image_judge always default
    # to nano unless the request explicitly overrides them.
    sm = getattr(req, "stageModels", None)
    default_model = _resolve_draft_default(getattr(req, "model", None))
    m_expansion = _resolve_stage_model("expansion", default_model, sm)
    m_draft = _resolve_stage_model("draft", default_model, sm)
    m_critique = _resolve_stage_model("critique", default_model, sm)
    m_image_judge = _resolve_stage_model("image_judge", default_model, sm)
    m_vision = _resolve_vision_model(sm)

    # Resolve author-diversity mode/cap (request field > env default > off).
    # In "auto" mode the concept-extraction call also returns a perspective
    # budget, so no extra LLM call is added.
    div_mode, div_cap = _resolve_diversity(getattr(req, "diversityAuthors", None))

    # 1. Parallel: query planner (top orchestrator) ‖ raw-query wide pull -----
    # The planner always runs (it also yields the diversity budget); the raw
    # query retrieves in parallel as the anchor pool.
    t_par = time.monotonic()
    planner_task = asyncio.create_task(
        extract_concepts_ex(query, model=m_expansion, max_authors=max(2, div_cap or _DIVERSITY_MAX))
    )
    candidates_task = asyncio.create_task(_wide_candidates(query, book_slugs, pool))
    plan_qp, (candidates, retr_meta) = await asyncio.gather(planner_task, candidates_task)
    concepts = plan_qp.concepts
    facets = plan_qp.facets
    effective_diversity = (
        plan_qp.suggested_authors if div_mode == "auto"
        else (div_cap if div_mode == "fixed" else 0)
    )

    # 1b. Multi-query retrieval: fan out the planner's queries (parallel) and
    # RRF-merge with the raw-query anchor pool.
    if _MULTI_QUERY and plan_qp.queries:
        extra = await _multi_query_candidates(plan_qp.queries, book_slugs, pool)
        if extra:
            candidates = _rrf_merge([candidates, extra])
    timings["parallel_extract_retrieve_ms"] = int((time.monotonic() - t_par) * 1000)
    logger.info("deep_tutor concepts=%s facets=%d queries=%d candidates=%d diversity=%s(target=%d) in %dms",
                concepts, len(facets), len(plan_qp.queries), len(candidates), div_mode, effective_diversity,
                timings["parallel_extract_retrieve_ms"])

    # 2. Density-score + expand + rerank --------------------------------------
    t_dens = time.monotonic()
    sources, collections_hit = await asyncio.to_thread(
        _density_select, query, concepts, candidates,
        book_slugs=book_slugs, top_sections=_TOP_SECTIONS, final_top_n=_FINAL_TOP_N,
        target_authors=effective_diversity,
    )
    timings["density_ms"] = int((time.monotonic() - t_dens) * 1000)

    # 2b. Coverage check (CRAG-lite): grade the selected sources against the
    # planner's facets; re-query any missing facet (cap 1) and re-rank. This is
    # what ensures e.g. BOTH the bias and the variance formula were retrieved.
    # Coverage gate: skip for simple questions (< 4 facets, no formula facet).
    # Fail-safe: if facets is empty, run coverage (conservative path — thin
    # sources may still benefit from the re-query, and the existing guard
    # `facets and sources` already handles the empty case by skipping).
    _needs_coverage: bool = bool(facets) and (
        len(facets) >= 4
        or any("$" in f or "formula" in f.lower() for f in facets)
    )
    if not _needs_coverage and COVERAGE_ON and facets:
        logger.info("coverage: skipped (simple)")
    if COVERAGE_ON and facets and sources and _needs_coverage:
        try:
            t_cov = time.monotonic()
            missing = await assess_coverage(query, facets, sources, model=m_expansion)
            if missing:
                logger.info("coverage: missing=%s", missing)
                seen = {s.chunkId for s in sources if s.chunkId}
                fills = await fill_missing_facets(missing, book_slugs, pool, seen)
                if fills:
                    sources = get_reranker().rerank(query, sources + fills, top_n=_FINAL_TOP_N)
                    logger.info("coverage: re-queried %d facet(s), +%d chunks", len(missing), len(fills))
            timings["coverage_ms"] = int((time.monotonic() - t_cov) * 1000)
        except Exception:  # noqa: BLE001
            logger.exception("coverage check failed; proceeding with current sources")

    # 2a. Synthesis plan (workflow A): build a thesis + evidence ledger +
    # author contrasts the draft will follow. Kicked off here so it overlaps
    # the image-judge branch below; awaited just before the draft.
    plan_on, m_plan = _resolve_plan_model(sm)
    plan_task: asyncio.Task | None = None
    if plan_on and sources:
        plan_task = asyncio.create_task(build_synthesis_plan(query, sources, model=m_plan))

    # 2b. Image candidates + two-tier pertinence judge (parallel-ish: we
    # need the top text sources first so co-location works).
    approved_figures: list = []
    images_status: str = "disabled"
    images_reason: str = ""
    images_cand_count: int = 0
    if _IMAGES_ENABLED and sources:
        t_img = time.monotonic()
        try:
            cands = await asyncio.to_thread(
                fetch_image_candidates, query, sources,
                book_slugs=book_slugs, pool=_IMAGE_POOL,
            )
            images_cand_count = len(cands or [])
            if cands:
                approved_figures = await judge_image_candidates(query, concepts, cands, t1_model=m_image_judge)
                if approved_figures:
                    images_status = "ok"
                else:
                    images_status = "all_rejected"
                    images_reason = (
                        f"Judge rejected all {images_cand_count} candidates"
                    )
            else:
                images_status = "no_candidates"
                images_reason = (
                    "No image candidates returned — likely the selected "
                    "books have no image collection ingested"
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("deep_tutor: image branch failed; continuing without figures")
            images_status = "error"
            images_reason = f"{type(exc).__name__}: {exc}"
        timings["images_ms"] = int((time.monotonic() - t_img) * 1000)
    elif not _IMAGES_ENABLED:
        images_status = "disabled"
        images_reason = "TUTOR_DEEP_IMAGES=0"
    elif not sources:
        images_status = "no_sources"
        images_reason = "No text sources retrieved; image branch skipped"

    yield {
        "type": "meta", "mode": req.mode, "books": book_slugs or [],
        "sourceCount": len(sources),
        "latencyMs": int((time.time() - t0) * 1000),
        "model": req.model, "concepts": concepts,
        "figureCount": len(approved_figures),
    }

    if not sources:
        empty = TutorAnswer(
            text="## No corpus coverage\nThe textbook corpus does not contain "
                 "material on this topic. Try a more specific query.\n",
            sections=["No corpus coverage"], citations=[], aspects={},
        )
        yield {"type": "token", "text": empty.text}
        yield {"type": "structured_output", "schema": "TutorAnswer",
               "data": empty.model_dump()}
        yield {"type": "retrieval_meta", "meta": retr_meta.model_dump()}
        yield {"type": "done"}
        return

    # Await the synthesis plan (started in 2a; overlapped the image branch).
    plan: SynthesisPlan | None = None
    if plan_task is not None:
        plan = await plan_task
        timings["plan_ms"] = int((time.monotonic() - t_dens) * 1000) - timings["density_ms"]

    # 3. Draft (streamed) -----------------------------------------------------
    t_draft = time.monotonic()
    sse_queue: asyncio.Queue = asyncio.Queue()

    def _emit_aspect_delta(aspect_key: str, delta: str) -> None:
        heading = ASPECT_HEADINGS.get(aspect_key, "")
        ev: dict = {"type": "token", "text": delta}
        if aspect_key != "_raw":
            ev["aspect"] = aspect_key
            ev["heading"] = heading
        sse_queue.put_nowait(ev)

    workflow = _resolve_workflow(req)

    async def _draft_coro():
        # Orchestrator-workers: per-author workers → streaming synthesizer.
        # Returns (None, _) when it can't beat the single draft (<2 authors,
        # workers failed) — then fall back to the single-draft path.
        if workflow == "orchestrator":
            from src.services.chat.agents.orchestrator_workers import (
                run_orchestrator_workers,
            )
            deep_o, aspects_o = await run_orchestrator_workers(
                query, sources, plan,
                orchestrator_model=_WORKER_MODEL, worker_model=_WORKER_MODEL,
                synth_model=m_draft,
                figures=approved_figures, on_aspect_delta=_emit_aspect_delta,
            )
            if deep_o is not None:
                return deep_o, aspects_o
            logger.info("orchestrator returned no result; falling back to single draft")
        # Long-context organize: hand the enlarged, token-budgeted pool to the
        # organizer model (deepseek-v4-pro) and let it organize the coherent
        # pieces — formulas, the central decomposition (MSE), real cases — into
        # the fields. Best-effort: on failure, fall back to the single draft.
        if workflow == "organize":
            org_pool = await asyncio.to_thread(
                _build_organize_pool, query, candidates, sources, _ORGANIZE_MAX_TOKENS
            )
            approx_tokens = sum(len(s.chunk or s.excerpt or "") for s in org_pool) // 4
            logger.info("organize: model=%s pool=%d/%d chunks ~%d tokens (budget %d)",
                        _ORGANIZE_MODEL, len(org_pool), len(candidates), approx_tokens,
                        _ORGANIZE_MAX_TOKENS)
            deep_org, aspects_org = await _stream_draft(
                query, org_pool, figures=approved_figures,
                on_aspect_delta=_emit_aspect_delta, model=_ORGANIZE_MODEL, plan=plan,
                instructions=ORGANIZER_PREAMBLE + DEEP_TUTOR_INSTRUCTIONS,
            )
            if deep_org is not None:
                return deep_org, aspects_org
            logger.info("organize returned no result; falling back to single draft")
        return await _stream_draft(
            query, sources, figures=approved_figures,
            on_aspect_delta=_emit_aspect_delta, model=m_draft, plan=plan,
        )

    draft_task = asyncio.create_task(_draft_coro())

    # Drain the SSE queue concurrently with the draft task.
    while not draft_task.done() or not sse_queue.empty():
        try:
            ev = await asyncio.wait_for(sse_queue.get(), timeout=0.1)
            yield ev
        except asyncio.TimeoutError:
            continue
    deep, aspects = await draft_task
    timings["draft_ms"] = int((time.monotonic() - t_draft) * 1000)

    # 4. Optional critique + refine ------------------------------------------
    augmented_sources = sources
    verdict: dict[str, Any] = {"complete": True, "missing": [],
                               "copy_paste_risk": "n/a", "reason": "skipped"}
    refine_iters = 0
    if _ENABLE_CRITIQUE:
        draft_text = assemble_markdown(aspects)
        verdict = await critique(draft_text, concepts, sources, model=m_critique)
        while (refine_iters < _MAX_REFINE_ITERS
               and not verdict.get("complete", True)
               and verdict.get("missing")):
            refine_iters += 1
            extra_concepts = list(dict.fromkeys(concepts + list(verdict["missing"])))[:4]
            extra_cands, _ = await _wide_candidates(query, book_slugs, pool)
            extra_sources, _coll = await asyncio.to_thread(
                _density_select, query, extra_concepts, extra_cands,
                book_slugs=book_slugs, top_sections=3, final_top_n=6,
            )
            augmented_sources = _merge_sources(augmented_sources, extra_sources)
            deep, aspects = await _stream_draft(query, augmented_sources,
                                                 figures=approved_figures, model=m_draft, plan=plan)
            verdict = await critique(assemble_markdown(aspects), concepts, augmented_sources,
                                     model=m_critique)

    # 5. Assemble final TutorAnswer payload -----------------------------------
    # #9: optionally have a vision model read each placed figure and explain
    # it in light of the concept just taught (off unless TUTOR_DEEP_VISION_EXPLAIN=1).
    vision_explanations = await build_vision_explanations(aspects, approved_figures, model=m_vision)
    # #8: semantic example-relevance (embedding cosine); None -> lexical fallback.
    example_relevance = await _embed_relevance(aspects)

    # Groq parity: Llama / gpt-oss drop backslashes from LaTeX commands when
    # serialising JSON, so KaTeX renders "mathbb{E}" as literal text. Run a
    # cheap polish pass through OpenAI nano that repairs missing backslashes
    # inside `$...$` and `$$...$$` regions. Only triggered when the draft
    # model is Groq-hosted; OpenAI / DeepSeek drafts skip the extra hop.
    from src.services.chat.llm.router import GROQ_MODEL_IDS  # noqa: PLC0415
    if m_draft in GROQ_MODEL_IDS:
        polish_tasks = {k: _polish_latex_via_llm(aspects.get(k, "") or "") for k in ASPECT_HEADINGS}
        polished = await asyncio.gather(*polish_tasks.values(), return_exceptions=True)
        for (k, _), result in zip(polish_tasks.items(), polished):
            if isinstance(result, str) and result:
                aspects[k] = result
        # Mirror polished aspects back onto the DeepTutorAnswer so downstream
        # code (and any later serialisation of `deep`) sees the corrected text.
        if deep is not None:
            for k, v in aspects.items():
                if hasattr(deep, k):
                    try:
                        setattr(deep, k, v)
                    except Exception:  # noqa: BLE001
                        pass
    answer = _convert_to_tutor_answer(deep, aspects, augmented_sources,
                                       approved_figures=approved_figures,
                                       vision_explanations=vision_explanations,
                                       example_relevance_override=example_relevance)
    final_payload = answer.model_dump()

    yield {"type": "structured_output", "schema": "TutorAnswer",
           "data": final_payload}
    yield {"type": "sources_full", "sources": _sources_to_payload(augmented_sources)}

    # Always emit ``figures_full`` (even empty) so the frontend can
    # distinguish "image branch produced nothing" from "event never
    # arrived". Companion ``figures_meta`` event carries the reason —
    # callers can surface it to the user instead of silent failure.
    yield {
        "type": "figures_full",
        "figures": [
            {
                "ref": f.ref,
                "book": f.book,
                "chapter": f.chapter,
                "caption": f.caption,
                "chart": f.url,
                "vision_used": f.vision_used,
                "vision_answer": f.vision_answer,
                "aspect_hint": f.aspect_hint,
                "figure_role": f.figure_role,
                "judge_confidence": f.judge_confidence,
            }
            for f in approved_figures
        ],
    }
    yield {
        "type": "figures_meta",
        "status": images_status,
        "reason": images_reason,
        "candidateCount": images_cand_count,
        "approvedCount": len(approved_figures),
    }

    retr_dump = retr_meta.model_dump()
    retr_dump["mode"] = (retr_dump.get("mode", "")
                        + f" | deep_tutor v2 (critique={_ENABLE_CRITIQUE},"
                        + f" refine_iters={refine_iters}, "
                        + f"copy_paste_risk={verdict.get('copy_paste_risk')})")
    retr_dump["timings"] = timings
    yield {"type": "retrieval_meta", "meta": retr_dump}

    yield {
        "type": "usage",
        "durationMs": int((time.time() - t0) * 1000),
        "promptChars": len(query),
        "completionChars": len(final_payload.get("text", "")),
        "estTokens": (len(query) + len(final_payload.get("text", ""))) // 4,
    }
    yield {"type": "done"}
