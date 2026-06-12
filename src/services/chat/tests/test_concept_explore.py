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


@pytest.mark.asyncio
async def test_concept_explore_never_touches_conversation_store(monkeypatch):
    import src.services.chat.store as store
    calls = []
    monkeypatch.setattr(store, "append_message", lambda **k: calls.append(k))
    monkeypatch.setattr(ce, "corpus_evidence", lambda *a, **k: [])
    monkeypatch.setattr(ce, "wiki_evidence", lambda *a, **k: [])

    async def fake_brief(term, evid, *, model):
        return "x"
    monkeypatch.setattr(ce, "_brief", fake_brief)
    _ = [e async for e in ce.concept_explore({"term": "t", "kind": "concept",
         "book_slug": "hansen", "section_id": "7.4", "conversationId": "abc"})]
    assert calls == []
