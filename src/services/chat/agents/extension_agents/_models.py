"""Per-stage model resolution for extension mode (isolated copy; do not import
the tutor resolver — keep the wall)."""
from __future__ import annotations

_TOP = "gpt-5.4-2026-03-17"        # orchestrator + judge: open reasoning
_MID = "gpt-5.4-nano-2026-03-17"   # polish
_CHEAP = "gpt-5.4-nano-2026-03-17" # analyst + augmentor: bounded tasks

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
