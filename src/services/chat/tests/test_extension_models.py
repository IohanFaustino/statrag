import os
from src.services.chat.agents.extension_agents._models import (
    resolve_stage_model, resolve_stage_temperature, STAGE_DEFAULTS, STAGE_TEMPERATURES
)


def test_defaults_top_for_orchestrator_and_judge():
    assert resolve_stage_model("orchestrator", None) == STAGE_DEFAULTS["orchestrator"]
    assert resolve_stage_model("judge", None) == STAGE_DEFAULTS["judge"]
    assert resolve_stage_model("analyst", None) == STAGE_DEFAULTS["analyst"]


def test_override_applies():
    assert resolve_stage_model("analyst", {"analyst": "gpt-5.4-2026-03-17"}) == "gpt-5.4-2026-03-17"


def test_unknown_override_falls_back_to_default():
    assert resolve_stage_model("analyst", {"analyst": ""}) == STAGE_DEFAULTS["analyst"]
    assert resolve_stage_model("analyst", {"other": "x"}) == STAGE_DEFAULTS["analyst"]


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


def test_polish_temperature_is_nonzero():
    assert STAGE_TEMPERATURES.get("polish", 0.0) > 0.0


def test_augmentor_temperature_is_nonzero():
    assert STAGE_TEMPERATURES.get("augmentor", 0.0) > 0.0


def test_orchestrator_temperature_is_zero():
    assert STAGE_TEMPERATURES.get("orchestrator", 0.0) == 0.0


def test_resolve_stage_temperature_returns_float():
    t = resolve_stage_temperature("polish")
    assert isinstance(t, float)
    assert t > 0.0
