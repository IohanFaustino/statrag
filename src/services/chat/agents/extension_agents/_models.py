"""Per-stage model resolution for extension mode (isolated copy; do not import
the tutor resolver — keep the wall).

Model ids come from settings (src.core) so they track the project's configured
OpenAI models rather than hard-coded literals that can drift out of existence."""
from __future__ import annotations

from src.core.config import settings

_TOP = settings.openai_model_full   # orchestrator + judge: open reasoning
_MID = settings.openai_model_nano   # polish
_CHEAP = settings.openai_model_nano # analyst + augmentor: bounded tasks

STAGE_DEFAULTS: dict[str, str] = {
    "orchestrator": _TOP,
    "judge": _TOP,
    "polish": _MID,
    "analyst": _CHEAP,
    "augmentor": _CHEAP,
}


def resolve_stage_model(stage: str, stage_models: dict | None) -> str:
    """Return the model id for a stage. Override wins if it names a non-empty
    value; otherwise the stage default. Unknown stage -> cheap default."""
    cand = (stage_models or {}).get(stage)
    if isinstance(cand, str) and cand.strip():
        return cand.strip()
    return STAGE_DEFAULTS.get(stage, _CHEAP)
