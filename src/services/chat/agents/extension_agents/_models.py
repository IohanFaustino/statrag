"""Per-stage model resolution for extension mode.

Model ids come from settings so they track the project's configured OpenAI
models and never drift to hard-coded literals."""
from __future__ import annotations

import os

from src.core.config import settings

_CHEAP = settings.openai_model_nano   # bounded tasks (all v2 stages default cheap)

STAGE_DEFAULTS: dict[str, str] = {
    "scope":       _CHEAP,
    "storyteller": _CHEAP,
    "editor":      _CHEAP,   # upgradeable via extensionModels["editor"]
    "miner":       _CHEAP,
    "writer":      _CHEAP,
    "judge":       _CHEAP,
}

STAGE_TEMPERATURES: dict[str, float] = {
    "scope": 0.0, "storyteller": 0.4, "editor": 0.3,
    "miner": 0.0, "writer": 0.2, "judge": 0.0,
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
