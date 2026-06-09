from src.services.chat.schemas import ChatRequest


def test_extension_is_valid_mode():
    req = ChatRequest(message="extend hansen ch7", mode="extension")
    assert req.mode == "extension"


def test_extension_knobs_default_none():
    req = ChatRequest(message="x", mode="extension")
    assert req.extensionMaxRounds is None
    assert req.extensionModels is None


def test_extension_knobs_accept_values():
    req = ChatRequest(
        message="x", mode="extension",
        extensionMaxRounds=2,
        extensionModels={"orchestrator": "gpt-5.4-2026-03-17", "analyst": "gpt-5.4-nano-2026-03-17"},
    )
    assert req.extensionMaxRounds == 2
    assert req.extensionModels["orchestrator"] == "gpt-5.4-2026-03-17"
