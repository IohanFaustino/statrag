"""The synthesis tail is collapsed: no workflow knob, no OW/organize modules."""
import importlib
import pytest


def test_tutorworkflow_field_removed():
    from src.services.chat.schemas._core import ChatRequest
    assert "tutorWorkflow" not in ChatRequest.model_fields


def test_orchestrator_and_harness_modules_gone():
    for mod in (
        "src.services.chat.agents.orchestrator_workers",
        "src.services.chat.agents.ow_deepagents",
        "src.services.chat.agents.ow_harness",
    ):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(mod)


def test_deep_tutor_has_no_workflow_resolver():
    import src.services.chat.agents.deep_tutor as dt
    assert not hasattr(dt, "_resolve_workflow")
    assert not hasattr(dt, "_build_organize_pool")
