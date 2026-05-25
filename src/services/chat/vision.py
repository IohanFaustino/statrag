"""Vision gate (ADR-004): decide when to call a vision model on a figure.

Algorithm (v1, caption-score-only):
  - Per-figure caption score from retrieval.
  - tau_high (default 0.62): score >= tau_high  -> include figure but DO NOT call vision.
    The caption is sufficient context.
  - tau_low (default 0.45):  tau_low <= score < tau_high -> CALL vision (uncertain region).
  - score < tau_low: skip figure entirely.
  - Cap on vision calls per request: max_calls (default 3). Excess go through caption-only path.

Mode-specific overrides: 'math' mode lowers tau_high (more eager to call vision);
'figures' mode uses same default.

Chinese-wall: imports only from ``src.core.*`` and sibling ``src.services.chat.*``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.services.chat.schemas import Figure

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VisionGateConfig:
    """Threshold configuration for the vision gate.

    Attributes:
        tau_high: Caption-score threshold above which vision is unnecessary.
            Figures at or above this score use caption-only context.
        tau_low: Caption-score threshold below which figures are skipped entirely.
            Figures between tau_low and tau_high trigger a vision call.
        max_calls: Maximum number of vision API calls per request. Figures beyond
            this cap fall back to caption-only even in the uncertain range.
    """

    tau_high: float = 0.62
    tau_low: float = 0.45
    max_calls: int = 3


@dataclass
class VisionDecision:
    """Result of the vision gate for a single figure.

    Attributes:
        figure: The :class:`~src.services.chat.schemas.Figure` evaluated.
        score: Caption-similarity score in [0, 1] from retrieval.
        action: One of ``"skip"``, ``"caption_only"``, or ``"call_vision"``.
        reason: Human-readable explanation of the decision.
    """

    figure: Figure
    score: float
    action: str   # "skip" | "caption_only" | "call_vision"
    reason: str


def vision_gate(
    figures: list[Figure],
    scores: list[float],
    *,
    config: VisionGateConfig | None = None,
) -> list[VisionDecision]:
    """Apply the vision gate to a list of (figure, score) pairs.

    Each figure receives one of three decisions:

    - ``"skip"``         — score below ``config.tau_low``; figure excluded entirely.
    - ``"caption_only"`` — score at or above ``config.tau_high`` (caption sufficient),
                           or the vision budget is exhausted.
    - ``"call_vision"``  — score in the uncertain region [tau_low, tau_high) and
                           within the per-request vision call budget.

    Args:
        figures: List of :class:`~src.services.chat.schemas.Figure` objects
            (from ``search_figures_with_scores``).
        scores: Parallel list of caption-similarity scores in [0, 1].
        config: Thresholds and budget. Defaults to :class:`VisionGateConfig`.

    Returns:
        List of :class:`VisionDecision`, one per input figure, in the same order.
    """
    cfg = config or VisionGateConfig()
    decisions: list[VisionDecision] = []
    calls_used = 0

    for fig, score in zip(figures, scores):
        if score < cfg.tau_low:
            decisions.append(
                VisionDecision(fig, score, "skip", f"score {score:.2f} < tau_low")
            )
        elif score >= cfg.tau_high:
            decisions.append(
                VisionDecision(
                    fig, score, "caption_only", f"caption sufficient (score {score:.2f})"
                )
            )
        elif calls_used < cfg.max_calls:
            decisions.append(
                VisionDecision(fig, score, "call_vision", "uncertain region; calling vision")
            )
            calls_used += 1
        else:
            decisions.append(
                VisionDecision(fig, score, "caption_only", "vision budget exhausted")
            )

    return decisions
