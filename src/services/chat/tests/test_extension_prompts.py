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


def test_storyteller_paragraph_division():
    """Prompt must instruct 2-4 paragraphs separated by blank lines."""
    low = P.STORYTELLER_PROMPT.lower()
    # blank-line / \n\n separation mentioned
    assert "\\n\\n" in P.STORYTELLER_PROMPT or "blank line" in low
    # multiple paragraph requirement
    assert "paragraph" in low


def test_storyteller_heading_plain_text():
    """Prompt must forbid math/$...$ in the heading field."""
    low = P.STORYTELLER_PROMPT.lower()
    assert "plain" in low or "plain text" in low or "no $" in low or "no math" in low
    # must tell model to spell math in words for headings
    assert "spell" in low or "words" in low


def test_editor_preserves_paragraph_breaks():
    """Editor prompt must instruct preservation of paragraph breaks."""
    assert "\\n\\n" in P.EDITOR_PROMPT or "paragraph break" in P.EDITOR_PROMPT.lower()
    assert "preserve" in P.EDITOR_PROMPT.lower() or "do not merge" in P.EDITOR_PROMPT.lower()


def test_writer_allows_short_paragraphs():
    """Writer prompt must allow 1-2 short paragraphs in body."""
    low = P.WRITER_PROMPT.lower()
    assert "paragraph" in low
    assert "\\n\\n" in P.WRITER_PROMPT or "blank line" in low
