"""Extension v2 prompt scaffolds."""
import src.services.chat.agents.extension_agents.prompts as P

ALL = [P.STORYTELLER_PROMPT, P.EDITOR_PROMPT, P.MINER_PROMPT, P.WRITER_PROMPT, P.JUDGE_PROMPT]


def test_all_prompts_use_xml_scaffold_and_pin_english():
    for p in ALL:
        assert "<role>" in p and "<task>" in p and "<rules>" in p
        assert "ENGLISH" in p.upper()


def test_storyteller_story_register_and_sequence():
    low = P.STORYTELLER_PROMPT.lower()
    assert "story" in low and "take" in low
    assert "author" in low and ("sequence" in low or "order" in low)


def test_editor_forbids_new_facts():
    low = P.EDITOR_PROMPT.lower()
    assert "no new fact" in low or "do not add" in low
    assert "10%" in P.EDITOR_PROMPT


def test_writer_forbids_writing_citations():
    low = P.WRITER_PROMPT.lower()
    assert "evidence_ids" in P.WRITER_PROMPT
    assert "never write citation" in low or "do not write citation" in low


def test_miner_has_gap_taxonomy():
    low = P.MINER_PROMPT.lower()
    for kind in ("formal-def", "derivation", "comparative", "application", "history"):
        assert kind in low
