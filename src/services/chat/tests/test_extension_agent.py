from src.services.chat.agents.extension_agents.agent import build_extension_agent


def test_builds_agent_with_subagents(monkeypatch):
    captured = {}
    def _fake_create(**kwargs):
        captured.update(kwargs)
        return object()
    import src.services.chat.agents.extension_agents.agent as A
    monkeypatch.setattr(A, "create_deep_agent", _fake_create)

    agent = build_extension_agent(
        stage_models=None,
        exclude_book="hansen-probability",
        all_slugs=["hansen-probability", "ross-probability"],
    )
    assert agent is not None
    names = {s["name"] for s in captured["subagents"]}
    assert names == {"analyst", "polish", "augmentor"}
    from src.services.chat.agents.extension_agents._models import STAGE_DEFAULTS
    assert captured["model"] == STAGE_DEFAULTS["orchestrator"]
    assert any("extension_skills" in s for s in captured["skills"])
