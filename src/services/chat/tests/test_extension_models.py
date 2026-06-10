import os
from src.services.chat.agents.extension_agents._models import (
    resolve_stage_model, resolve_stage_temperature, STAGE_DEFAULTS, STAGE_TEMPERATURES
)


def test_defaults_exist_for_all_v2_stages():
    # v1 orchestrator/analyst keys are gone; v2 keys must be present
    for stage in ("scope", "storyteller", "editor", "miner", "writer", "judge"):
        assert stage in STAGE_DEFAULTS, f"missing stage: {stage}"


def test_judge_default_is_cheap_not_top():
    from src.core.config import settings
    assert STAGE_DEFAULTS["judge"] != settings.openai_model_full
    assert STAGE_DEFAULTS["judge"] == settings.openai_model_nano


def test_mid_alias_exists_and_equals_nano():
    from src.services.chat.agents.extension_agents._models import _MID, _CHEAP
    # Both are nano today; having them as separate names enables future bumps.
    assert _MID == _CHEAP


def test_extension_judge_model_env_override(monkeypatch):
    monkeypatch.setenv("EXTENSION_JUDGE_MODEL", "custom-judge-model")
    assert resolve_stage_model("judge", None) == "custom-judge-model"


def test_extension_judge_model_env_empty_uses_default(monkeypatch):
    monkeypatch.delenv("EXTENSION_JUDGE_MODEL", raising=False)
    from src.core.config import settings
    assert resolve_stage_model("judge", None) == settings.openai_model_nano


def test_resolve_stage_temperature_returns_float():
    t = resolve_stage_temperature("storyteller")
    assert isinstance(t, float)
    assert t > 0.0


# ---------------------------------------------------------------------------
# v2 stage table tests (Tasks 2 assertions verbatim from plan)
# ---------------------------------------------------------------------------


def test_v2_stage_defaults_exist():
    from src.services.chat.agents.extension_agents._models import STAGE_DEFAULTS
    assert set(STAGE_DEFAULTS) == {"scope", "storyteller", "editor", "miner", "writer", "judge"}


def test_v2_override_and_fallback():
    from src.services.chat.agents.extension_agents._models import resolve_stage_model, STAGE_DEFAULTS
    assert resolve_stage_model("storyteller", {"storyteller": "x-model"}) == "x-model"
    assert resolve_stage_model("editor", None) == STAGE_DEFAULTS["editor"]
    assert resolve_stage_model("unknown-stage", None)  # falls back, never raises
