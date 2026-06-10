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
    # Model is now a concrete ChatOpenAI (explicit api_key, not a bare id string)
    # so deepagents does not fall back to an env-var lookup that misses .env.
    orch = captured["model"]
    model_name = getattr(orch, "model_name", None) or getattr(orch, "model", None)
    assert model_name is not None  # v1 orchestrator stage removed in v2; agent.py deleted later
    # subagent models are concrete clients too (not strings)
    assert not isinstance(captured["subagents"][0]["model"], str)
    assert any("extension_skills" in s for s in captured["skills"])
