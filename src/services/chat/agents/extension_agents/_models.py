"""Per-stage model resolution for extension mode.

Model ids come from settings so they track the project's configured OpenAI
models and never drift to hard-coded literals."""
from __future__ import annotations

import os

from src.core.config import settings

_TOP   = settings.openai_model_full   # orchestrator: open reasoning
_MID   = settings.openai_model_nano   # polish — semantically separate from _CHEAP
_CHEAP = settings.openai_model_nano   # analyst, augmentor, judge: bounded tasks

STAGE_DEFAULTS: dict[str, str] = {
    "orchestrator": _TOP,
    "judge":        _CHEAP,  # judge only parses COVERAGE markers + re-delegates
    "polish":       _MID,
    "analyst":      _CHEAP,
    "augmentor":    _CHEAP,
}

STAGE_TEMPERATURES: dict[str, float] = {
    "orchestrator": 0.0,   # needs consistency for gap planning
    "judge":        0.0,   # deterministic coverage check
    "polish":       0.3,   # more varied curation
    "analyst":      0.0,
    "augmentor":    0.2,   # better footnote prose variety
}


def resolve_stage_model(stage: str, stage_models: dict | None) -> str:
    """Return the model id for a stage.
    Priority: per-request override > EXTENSION_JUDGE_MODEL env (judge only) > stage default."""
    cand = (stage_models or {}).get(stage)
    if isinstance(cand, str) and cand.strip():
        return cand.strip()
    if stage == "judge":
        env_val = os.environ.get("EXTENSION_JUDGE_MODEL", "").strip()
        if env_val:
            return env_val
    return STAGE_DEFAULTS.get(stage, _CHEAP)


def resolve_stage_temperature(stage: str) -> float:
    """Return the generation temperature for a stage."""
    return STAGE_TEMPERATURES.get(stage, 0.0)
