"""Two-tier pertinence judge for image candidates.

Tier 1 — caption-only nano LLM (cheap, ~150ms parallel per candidate):
    Inputs: query, concepts, image caption + minimal metadata.
    Output JSON: {include, role, confidence, aspect_hint, reason}.

Tier 2 — optional vision LLM (gpt-4o-mini) for borderline confidence
    (default 0.4..0.7). Up to 2 calls per query (env-capped).

The judge returns a sorted list of approved figures (max 3) with
``aspect_hint`` so the draft prompt can place them in the right
DeepTutorAnswer section.

Chinese-wall: imports only from ``src.core.*`` and sibling
``src.services.chat.*``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import openai as _openai

from src.core.config import settings
from src.services.chat._fences import strip_fences
from src.services.chat.retrievers.image_density import FigureCandidate
from src.services.chat.schemas import Figure
from src.services.chat.schemas.output import FigureRef

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

_MAX_FIGURES = int(os.environ.get("TUTOR_DEEP_IMAGES_MAX", "3"))
_TIER2_MAX_CALLS = int(os.environ.get("TUTOR_DEEP_VISION_MAX", "2"))
_TIER2_ENABLED = os.environ.get("TUTOR_DEEP_VISION_DISABLE", "0") != "1"
_TIER1_INCLUDE_THRESHOLD = float(os.environ.get("TUTOR_DEEP_TIER1_INCLUDE", "0.7"))
_TIER1_EXCLUDE_THRESHOLD = float(os.environ.get("TUTOR_DEEP_TIER1_EXCLUDE", "0.4"))
_MIN_CAPTION_CHARS = 10

_TIER1_PROMPT = """\
<role>
You are the TIER-1 IMAGE PERTINENCE AUDITOR for an AI tutor over statistics /
econometrics / ML textbooks. You make a caption-only judgement; a slower
vision tier verifies borderline cases.
</role>

<context>
You receive `<query>`, `<concepts>`, and `<figure>` (book + chapter + ref +
caption + co-located flag) for ONE candidate figure. Confidences in the
escalation band (0.4-0.7) trigger the Tier-2 vision pass; high/low confidence
short-circuits it. False includes flood the answer with decorative images;
false excludes lose load-bearing diagrams.
</context>

<task>
Return ONLY a JSON object with EXACTLY this shape:

{
  "include": true|false,
  "role": "diagram"|"graph"|"chart"|"table"|"equation"|"photo"|"other",
  "confidence": 0.0..1.0,
  "aspect_hint": "tldr"|"definition"|"formal_statement"|"example_intuition"|"applications"|"further_reading",
  "reason": "<= 25 words"
}
</task>

<rules>
Decision criteria (highest weight first):
- Direct relevance: does the figure illustrate the central concept(s) of the query?
- Pedagogical role: diagrams, graphs, charts, tables, and equations have high value; decorative photos have low value.
- Self-contained: caption + figure stands on its own without external context.

Default exclude:
- Empty / trivial caption (< 10 chars meaningful content).
- Decorative photo of people / scenery / book cover with no technical content.
- Captions describing code listings, exercises, or chapter front-matter rather than illustrations.

When borderline (caption could be useful but you can't tell), set
confidence between 0.4 and 0.7 so the vision tier can verify.

Aspect mapping guide:
- "definition" — formal definitional diagram / venn / set diagram.
- "formal_statement" — equation, derivation, or proof sketch.
- "example_intuition" — informal illustration, analogy, schematic, worked-example chart, scatter, regression line, table of cases, or a bias-variance / comparison curve that builds intuition.
- "applications" — figure tied to a real-world use-case or domain application.
- "further_reading" — high-level roadmap diagram.
</rules>

<output>
The JSON object only — no preamble, no markdown.
</output>
"""


def _aclient() -> _openai.AsyncOpenAI:
    return _openai.AsyncOpenAI(api_key=settings.openai_api_key)


async def _judge_one_caption(
    query: str,
    concepts: list[str],
    candidate: FigureCandidate,
    t1_model: str | None = None,
) -> dict[str, Any]:
    """Tier-1 caption-only verdict for one candidate.

    When the caption is missing / too short to judge, return a
    *borderline* verdict (confidence in the Tier-2 escalation band)
    rather than a hard exclude — empty captions are common in our
    OCR-derived image payloads and should route to vision verification.
    """
    fig = candidate.figure
    caption = (fig.caption or "").strip()
    if len(caption) < _MIN_CAPTION_CHARS:
        return {
            "include": False, "role": "other",
            "confidence": (_TIER1_INCLUDE_THRESHOLD + _TIER1_EXCLUDE_THRESHOLD) / 2.0,
            "aspect_hint": None,
            "reason": "empty / short caption — defer to vision",
        }
    user = (
        f"<query>{query}</query>\n"
        f"<concepts>{json.dumps(concepts)}</concepts>\n"
        f"<figure>\n"
        f"  book: {fig.book} chapter: {fig.chapter}\n"
        f"  ref: {fig.ref}\n"
        f"  caption: {caption[:600]}\n"
        f"  co_located_with_top_sources: {candidate.co_located}\n"
        f"</figure>"
    )
    try:
        oa = _aclient()
        # deepseek override not supported on this OpenAI JSON path -> nano.
        t1 = t1_model if (t1_model and not t1_model.startswith("deepseek")) else settings.openai_model_nano
        resp = await oa.chat.completions.create(
            model=t1,
            messages=[
                {"role": "system", "content": _TIER1_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_completion_tokens=200,
            response_format={"type": "json_object"},
        )
        raw = strip_fences(resp.choices[0].message.content or "{}")
        data = json.loads(raw)
        return {
            "include": bool(data.get("include", False)),
            "role": str(data.get("role", "other")),
            "confidence": float(data.get("confidence", 0.0) or 0.0),
            "aspect_hint": data.get("aspect_hint") or None,
            "reason": str(data.get("reason", ""))[:200],
        }
    except Exception:  # noqa: BLE001
        logger.exception("tier1 caption judge failed; defaulting to exclude")
        return {
            "include": False, "role": "other", "confidence": 0.0,
            "aspect_hint": None, "reason": "judge error",
        }


_TIER2_PROMPT = """\
<role>
You are the TIER-2 VISION VERIFIER. Your verdict is final for borderline
candidates that Tier-1 (caption-only) could not decide.
</role>

<context>
You receive the user's query plus an image and its caption (the same caption
Tier-1 saw). The pipeline only escalates borderline confidences here, so the
expected base rate of useful figures is high — but decorative or unreadable
images still slip through.
</context>

<task>
Look at the image and the caption. Decide include/exclude and pick the best
DeepTutorAnswer aspect for it. Return ONLY a JSON object:
{include, confidence, aspect_hint, reason}.
</task>

<rules>
- `confidence` is a float in [0.0, 1.0].
- `aspect_hint` is one of: tldr, definition, formal_statement,
  example_intuition, applications, further_reading.
- Be strict: if the image is decorative / off-topic / unreadable, exclude.
</rules>

<output>
The JSON object only — no preamble, no markdown.
</output>
"""


_PATH_REWRITES_RUNTIME: list[tuple[str, str]] = [
    # Same remap as the labelling script: stored absolute paths point at
    # a tree that has since been relocated under /Documents/Converters/.
    ("/home/iohan/Documents/Books/", "/home/iohan/Documents/Converters/Books/"),
]


def resolve_image_for_vision(chart_url: str) -> str | None:
    """Public alias of :func:`_resolve_image_for_vision` for sibling agents."""
    return _resolve_image_for_vision(chart_url)


def _resolve_image_for_vision(chart_url: str) -> str | None:
    """Convert a stored image reference into something the OpenAI vision
    API can read.

    - HTTP(S) URLs are passed through unchanged.
    - ``/api/figures?path=...`` references and bare local paths are
      resolved on disk and embedded as base64 data URIs.
    Returns ``None`` when the file cannot be read.
    """
    if not chart_url:
        return None
    if chart_url.startswith(("http://", "https://", "data:")):
        return chart_url
    import base64
    import os.path as _osp
    from urllib.parse import unquote

    path: str | None = None
    marker = "path="
    if marker in chart_url:
        i = chart_url.find(marker)
        path = unquote(chart_url[i + len(marker):])
    elif chart_url.startswith("/"):
        path = chart_url

    if not path:
        return None
    for old, new in _PATH_REWRITES_RUNTIME:
        if path.startswith(old):
            path = new + path[len(old):]
            break

    try:
        if not _osp.exists(path):
            return None
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    if len(data) > 8 * 1024 * 1024:
        return None
    suffix = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    mime = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "gif": "image/gif", "webp": "image/webp",
    }.get(suffix, "image/jpeg")
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


async def _judge_one_vision(
    query: str,
    candidate: FigureCandidate,
    tier1: dict[str, Any],
) -> dict[str, Any]:
    """Tier-2 vision verdict. Best-effort: failures fall back to tier1."""
    fig = candidate.figure
    image_ref = _resolve_image_for_vision(fig.chart)
    if not image_ref:
        return tier1
    user_content: list[dict] = [
        {"type": "text", "text": (
            f"<query>{query}</query>\n"
            f"<caption>{(fig.caption or '')[:400]}</caption>\n"
            f"<tier1_verdict>{json.dumps(tier1)}</tier1_verdict>"
        )},
        {"type": "image_url", "image_url": {"url": image_ref}},
    ]
    oa = _aclient()
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            resp = await oa.chat.completions.create(
                model=os.environ.get("TUTOR_DEEP_VISION_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": _TIER2_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.0,
                max_completion_tokens=200,
                response_format={"type": "json_object"},
            )
            raw = strip_fences(resp.choices[0].message.content or "{}")
            data = json.loads(raw)
            return {
                "include": bool(data.get("include", tier1["include"])),
                "role": tier1.get("role", "other"),
                "confidence": float(data.get("confidence", tier1["confidence"]) or 0.0),
                "aspect_hint": data.get("aspect_hint") or tier1.get("aspect_hint"),
                "reason": str(data.get("reason", tier1.get("reason", "")))[:200],
                "vision_used": True,
            }
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            msg = str(exc).lower()
            if "rate" in msg or "429" in msg or "timeout" in msg:
                await asyncio.sleep(min(2 ** attempt * 4, 30))
                continue
            break
    logger.exception("tier2 vision judge failed (%s); keeping tier1 verdict", last_err)
    return {**tier1, "vision_used": False}


async def judge_image_candidates(
    query: str,
    concepts: list[str],
    candidates: list[FigureCandidate],
    t1_model: str | None = None,
) -> list[FigureRef]:
    """Run two-tier judge over *candidates* and return approved FigureRef list.

    Output ordered by confidence desc, capped at ``TUTOR_DEEP_IMAGES_MAX``
    (default 3). *t1_model* overrides the Tier-1 caption-judge model.
    """
    if not candidates:
        return []

    # ---- Tier 1 (parallel) ----
    tier1_verdicts = await asyncio.gather(
        *(_judge_one_caption(query, concepts, c, t1_model) for c in candidates)
    )

    decisions: list[tuple[FigureCandidate, dict[str, Any]]] = []
    borderline: list[tuple[FigureCandidate, dict[str, Any]]] = []
    for cand, v in zip(candidates, tier1_verdicts):
        conf = v.get("confidence", 0.0)
        if v.get("include") and conf >= _TIER1_INCLUDE_THRESHOLD:
            decisions.append((cand, v))
        elif not v.get("include") and conf >= _TIER1_INCLUDE_THRESHOLD:
            # confidently excluded — skip
            continue
        elif _TIER2_EXCLUDE_OK(conf):
            # confidently exclude even when "include" is False
            continue
        else:
            borderline.append((cand, v))

    # ---- Tier 2 (vision, capped) ----
    if _TIER2_ENABLED and borderline:
        tier2_targets = borderline[:_TIER2_MAX_CALLS]
        tier2_verdicts = await asyncio.gather(
            *(_judge_one_vision(query, c, v) for c, v in tier2_targets)
        )
        for (cand, _v1), v2 in zip(tier2_targets, tier2_verdicts):
            if v2.get("include"):
                decisions.append((cand, v2))

    # Rank by confidence then dense similarity ---------------------------------
    decisions.sort(key=lambda t: (t[1].get("confidence", 0.0), t[0].combined),
                   reverse=True)

    approved: list[FigureRef] = []
    for cand, v in decisions[:_MAX_FIGURES]:
        fig: Figure = cand.figure
        approved.append(FigureRef(
            ref=fig.ref,
            book=fig.book,
            chapter=fig.chapter,
            caption=fig.caption,
            url=fig.chart,
            vision_used=bool(v.get("vision_used", False)),
            vision_answer=v.get("reason") if v.get("vision_used") else None,
            aspect_hint=v.get("aspect_hint"),
            figure_role=v.get("role", "other"),
            judge_confidence=float(v.get("confidence", 0.0) or 0.0),
            judge_reason=str(v.get("reason", "")),
        ))
    return approved


def _TIER2_EXCLUDE_OK(conf: float) -> bool:
    """Below this confidence, an 'exclude' verdict is solid enough to keep
    without paying for vision verification."""
    return conf <= _TIER1_EXCLUDE_THRESHOLD
