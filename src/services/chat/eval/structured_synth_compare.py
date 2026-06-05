"""Lightweight A/B/C comparison for the structured-synth cycle (few calls).

Runs the bias-variance query through harness levels 5 (current C), 6 (A), 7 (B),
one run each, scoring clean-math / component-formulas / bullet-density / latency /
tokens. Needs deepagents installed + OPENAI_API_KEY. Run:
  .venv/bin/python -m src.services.chat.eval.structured_synth_compare
"""
from __future__ import annotations

# ── Metric helpers (no heavy deps — safe for top-level import) ──────────────
import re

_BAD_MATH_RE = re.compile(r"\\\$\(|\\\)\$")
_FORMULA_RE = re.compile(r"\$\$[^$]*\b(MSE|Bias|Var)\b[^$]*\$\$|\$[^$]*\\operatorname")


def count_clean_math_violations(text: str) -> int:
    """Count occurrences of malformed math escapes (e.g. \\$(x\\)$)."""
    return len(_BAD_MATH_RE.findall(text or ""))


def has_component_formulas(text: str) -> bool:
    """True when the text contains at least one inline \\operatorname formula
    AND a display formula with a known bias-variance component."""
    t = text or ""
    inline = bool(re.search(r"\$[^$]*\\operatorname|\$[^$]*=[^$]*\$", t))
    return inline and bool(_FORMULA_RE.search(t))


def count_bullets(text: str) -> int:
    """Count bold-label bullets (lines matching '- **...')."""
    return len(re.findall(r"(?m)^\s*-\s+\*\*", text or ""))


# ── Live comparison run (all heavy imports are LAZY — inside run()) ─────────

QUERY = "Compare how different authors define and motivate the bias-variance tradeoff."
BOOKS = ["hansen", "wooldridge", "stock_watson", "gujarati", "baltagi", "pesaran", "islp", "murphy"]
TOP_K = 12
LEVELS = (5, 6, 7)
LEVEL_LABELS = {5: "C (current)", 6: "A", 7: "B"}

_ROOT_PATH = None  # resolved lazily


def _root() -> "Path":
    from pathlib import Path
    global _ROOT_PATH
    if _ROOT_PATH is None:
        _ROOT_PATH = Path(__file__).resolve().parents[4]
    return _ROOT_PATH


async def run() -> None:
    """Retrieve sources once, then run harness levels 5/6/7 and print a scoring table."""
    import asyncio
    import os
    import time
    from pathlib import Path

    # Heavy deps — kept inside run() so module-level import stays light
    from src.services.chat.retrieval import hybrid_search  # type: ignore
    from src.services.chat.agents.orchestrator_workers import run_orchestrator_workers  # noqa

    # ── 1. Single retrieval call, reused across all arms ──────────────────
    print(f"Retrieving sources for query: {QUERY!r}")
    sources, _ctx = hybrid_search(QUERY, book_slugs=BOOKS, top_k=TOP_K, rerank=False)
    print(f"  → {len(sources)} sources from "
          f"{len({(s.authors_short or s.book) for s in sources})} authors")

    # plan=None lets orchestrator_workers fall back to per-author task split
    plan = None

    # ── 2. Run each arm ───────────────────────────────────────────────────
    rows: list[dict] = []
    for level in LEVELS:
        os.environ["TUTOR_OW_HARNESS"] = str(level)
        label = LEVEL_LABELS[level]
        print(f"\nRunning harness level {level} ({label}) …")
        t0 = time.monotonic()
        try:
            answer, aspects = await run_orchestrator_workers(
                QUERY, sources, plan
            )
            latency = time.monotonic() - t0

            if answer is None:
                text_blob = ""
                in_tok = out_tok = 0
            else:
                # Concatenate all aspect fields into one blob for metric scoring
                text_blob = "\n\n".join(
                    str(v) for v in aspects.values() if v
                ) or (answer.answer or "")
                in_tok = getattr(answer, "in_tokens", 0) or 0
                out_tok = getattr(answer, "out_tokens", 0) or 0

            rows.append({
                "level": level,
                "label": label,
                "clean_math_violations": count_clean_math_violations(text_blob),
                "has_component_formulas": has_component_formulas(text_blob),
                "bullet_count": count_bullets(text_blob),
                "latency_s": round(latency, 2),
                "in_tok": in_tok,
                "out_tok": out_tok,
                "ok": True,
            })
        except Exception as exc:
            latency = time.monotonic() - t0
            print(f"  ✗ level {level} failed: {exc}")
            rows.append({
                "level": level,
                "label": label,
                "clean_math_violations": -1,
                "has_component_formulas": False,
                "bullet_count": 0,
                "latency_s": round(latency, 2),
                "in_tok": 0,
                "out_tok": 0,
                "ok": False,
                "error": str(exc),
            })

    # ── 3. Print comparison table ─────────────────────────────────────────
    print("\n\n## Structured-Synth A/B/C Comparison\n")
    hdr = f"{'Level':<8} {'Label':<14} {'CMV':>5} {'HasFormula':>11} {'Bullets':>8} {'Latency_s':>10} {'in_tok':>8} {'out_tok':>8}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(
            f"{r['level']:<8} {r['label']:<14} "
            f"{r['clean_math_violations']:>5} "
            f"{str(r['has_component_formulas']):>11} "
            f"{r['bullet_count']:>8} "
            f"{r['latency_s']:>10.2f} "
            f"{r['in_tok']:>8} "
            f"{r['out_tok']:>8}"
        )

    # ── 4. Write markdown artifact ────────────────────────────────────────
    out_dir = _root() / "docs" / "superpowers" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact = out_dir / "2026-06-04-structured-synth-compare.md"

    md_lines = [
        "# Structured-Synth A/B/C Comparison",
        "",
        f"_Query: {QUERY}_",
        "",
        f"_Sources: {len(sources)} chunks · {len({(s.authors_short or s.book) for s in sources})} authors · top_k={TOP_K}_",
        "",
        "| Level | Label | CMV | HasFormula | Bullets | Latency_s | in_tok | out_tok | ok |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        md_lines.append(
            f"| {r['level']} | {r['label']} | {r['clean_math_violations']} "
            f"| {r['has_component_formulas']} | {r['bullet_count']} "
            f"| {r['latency_s']:.2f} | {r['in_tok']} | {r['out_tok']} "
            f"| {'✓' if r['ok'] else '✗'} |"
        )
    md_lines += [
        "",
        "**CMV** = clean_math_violations (lower=better)",
        "**HasFormula** = has_component_formulas",
        "**Bullets** = bold-label bullet count",
        "",
    ]
    artifact.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"\nArtifact written → {artifact}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(run())
