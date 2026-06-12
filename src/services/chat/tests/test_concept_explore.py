# src/services/chat/tests/test_concept_explore.py
import pytest
from src.services.chat import concept_explore as ce
from src.services.chat.research import Evidence


@pytest.mark.asyncio
async def test_seed_builds_corpus_and_wiki_chips(monkeypatch):
    monkeypatch.setattr(ce, "corpus_evidence", lambda *a, **k: [
        Evidence(subject_id="t", kind="corpus", text="passage about LLN",
                 meta={"book_slug": "hansen", "book_name": "Probability",
                       "authors": "Hansen", "section_id": "7.4", "pages": "120", "chunk_id": "x"})])
    monkeypatch.setattr(ce, "wiki_evidence", lambda *a, **k: [
        Evidence(subject_id="t", kind="wikipedia", text="LLN says averages converge",
                 meta={"title": "Law of large numbers", "url": "https://en.wikipedia.org/wiki/LLN"})])

    async def fake_brief(term, evid, *, model):
        return "The law of large numbers says sample averages converge to the mean."
    monkeypatch.setattr(ce, "_brief", fake_brief)

    body = {"term": "law of large numbers", "kind": "theorem",
            "book_slug": "hansen", "section_id": "7.4", "conversationId": "abc"}
    events = [e async for e in ce.concept_explore(body)]
    payload = next(e for e in events if e["type"] == "concept_seed")
    kinds = {c["kind"] for c in payload["citations"]}
    assert kinds == {"corpus", "wikipedia"}
    assert "converge" in payload["brief"]
    assert any(c.get("url", "").endswith("/LLN") for c in payload["citations"])


def test_concept_explore_module_never_imports_conversation_store():
    import inspect
    import src.services.chat.concept_explore as ce_mod
    src_text = inspect.getsource(ce_mod)
    # the side-chat must never read/write the conversation message store
    for forbidden in ("append_message", "get_messages", "import src.services.chat.store",
                      "from src.services.chat.store", "from src.services.chat import store"):
        assert forbidden not in src_text, f"concept_explore must not reference {forbidden!r}"
