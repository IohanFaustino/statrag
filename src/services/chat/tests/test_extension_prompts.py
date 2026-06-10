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


def test_orchestrator_has_footnote_density_rule():
    assert "2 footnote" in P.ORCHESTRATOR_PROMPT or ">= 2" in P.ORCHESTRATOR_PROMPT or "≥ 2" in P.ORCHESTRATOR_PROMPT


def test_orchestrator_has_orphan_footnote_merge():
    assert "orphan" in P.ORCHESTRATOR_PROMPT.lower() or "not match" in P.ORCHESTRATOR_PROMPT.lower()


def test_orchestrator_strong_english_rule():
    assert "translate" in P.ORCHESTRATOR_PROMPT.lower() or "english" in P.ORCHESTRATOR_PROMPT.lower()


def test_analyst_has_gap_taxonomy():
    low = P.ANALYST_PROMPT.lower()
    # must reference at least 3 of the 4 gap types
    types_found = sum([
        "formal definition" in low or "formally defined" in low,
        "formula" in low or "derivation" in low,
        "comparative" in low or "comparison" in low,
        "application" in low or "example" in low,
    ])
    assert types_found >= 3


def test_augmentor_has_fit_rubric():
    assert "score" in P.AUGMENTOR_PROMPT.lower() or "relevance" in P.AUGMENTOR_PROMPT.lower()
    assert "discard" in P.AUGMENTOR_PROMPT.lower()


def test_augmentor_has_latex_examples():
    assert "$E[" in P.AUGMENTOR_PROMPT or r"\mu" in P.AUGMENTOR_PROMPT or "$$" in P.AUGMENTOR_PROMPT


def test_augmentor_has_coverage_format():
    assert "# COVERAGE:" in P.AUGMENTOR_PROMPT
    assert "done" in P.AUGMENTOR_PROMPT
    assert "unfilled" in P.AUGMENTOR_PROMPT


def test_polish_keeps_formal_structure():
    low = P.POLISH_PROMPT.lower()
    assert "formal" in low or "notation" in low or "definition" in low


def test_judge_has_english_check():
    assert "english" in P.JUDGE_PROMPT.lower() or "translate" in P.JUDGE_PROMPT.lower()


# ---------------------------------------------------------------------------
# T5: parallel analyst fan-out directive
# ---------------------------------------------------------------------------

def test_orchestrator_directs_parallel_analyst_fanout():
    """ORCHESTRATOR_PROMPT must explicitly direct the model to issue all analyst
    task calls in a single message so LangGraph ToolNode runs them concurrently."""
    low = P.ORCHESTRATOR_PROMPT.lower()
    assert "single message" in low or "all at once" in low or "parallel" in low


def test_orchestrator_parallel_directive_is_in_task_section():
    """The parallel fan-out instruction must be inside the <task> block, not
    buried in <rules>, so it is the most salient call-to-action."""
    task_block = P.ORCHESTRATOR_PROMPT.split("<task>")[1].split("</task>")[0]
    low = task_block.lower()
    assert "single message" in low or "parallel" in low


def test_orchestrator_bans_sequential_analyst_pattern():
    """The prompt must also explicitly forbid sending analyst calls one at a time."""
    low = P.ORCHESTRATOR_PROMPT.lower()
    assert "one at a time" in low or "not.*one.*at.*a.*time" in low or "not send analyst" in low or "do not send" in low
