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


from src.services.chat.schemas import ExtensionDigest, ExtensionPoint, ExtensionFootnote


def test_extension_digest_shape():
    d = ExtensionDigest(
        book="hansen-probability", chapter="ch07",
        points=[ExtensionPoint(
            title="Law of Large Numbers",
            curated_text="The LLN states the sample mean converges to the expectation.",
            footnotes=[ExtensionFootnote(
                marker="1", body="Chebyshev gives $P(|X-\\mu|\\ge k)\\le \\sigma^2/k^2$.",
                source="ross-probability ch05", kind="corpus")],
        )],
        unfilled_gaps=[],
    )
    assert d.points[0].footnotes[0].kind == "corpus"


def test_extension_digest_strict_safe():
    import json
    schema = json.dumps(ExtensionDigest.model_json_schema())
    assert '"additionalProperties": true' not in schema
    assert "patternProperties" not in schema
