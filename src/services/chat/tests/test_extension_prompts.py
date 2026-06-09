import src.services.chat.agents.extension_agents.prompts as P

PROMPTS = [P.ORCHESTRATOR_PROMPT, P.ANALYST_PROMPT, P.POLISH_PROMPT,
           P.AUGMENTOR_PROMPT, P.JUDGE_PROMPT]


def test_every_prompt_is_xml_tagged():
    for p in PROMPTS:
        assert "<role>" in p and "</role>" in p
        assert "<context>" in p and "</context>" in p
        assert "<task>" in p and "</task>" in p


def test_augmentor_states_footnote_only_rule():
    assert "footnote" in P.AUGMENTOR_PROMPT.lower()
    assert "<rules>" in P.AUGMENTOR_PROMPT


def test_polish_states_curate_not_summarize():
    low = P.POLISH_PROMPT.lower()
    assert "not a summary" in low or "do not summarize" in low
