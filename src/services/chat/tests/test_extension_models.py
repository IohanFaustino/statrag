from src.services.chat.agents.extension_agents._models import resolve_stage_model, STAGE_DEFAULTS


def test_defaults_top_for_orchestrator_and_judge():
    assert resolve_stage_model("orchestrator", None) == STAGE_DEFAULTS["orchestrator"]
    assert resolve_stage_model("judge", None) == STAGE_DEFAULTS["judge"]
    assert resolve_stage_model("analyst", None) == STAGE_DEFAULTS["analyst"]


def test_override_applies():
    assert resolve_stage_model("analyst", {"analyst": "gpt-5.4-2026-03-17"}) == "gpt-5.4-2026-03-17"


def test_unknown_override_falls_back_to_default():
    assert resolve_stage_model("analyst", {"analyst": ""}) == STAGE_DEFAULTS["analyst"]
    assert resolve_stage_model("analyst", {"other": "x"}) == STAGE_DEFAULTS["analyst"]
