"""Unit tests for the chained question-decomposition query planner."""
from src.services.chat.prompts import deep_tutor as P


def test_chain_prompts_exist_and_mention_keys():
    assert "sub_questions" in P.PLANNER_DECOMPOSE_PROMPT
    assert "application" in P.PLANNER_DECOMPOSE_PROMPT.lower()
    assert "related" in P.PLANNER_DECOMPOSE_PROMPT.lower()
    assert "items" in P.PLANNER_EXPAND_PROMPT
    for k in ("concept", "query", "facet"):
        assert k in P.PLANNER_EXPAND_PROMPT
    for k in ("concepts", "perspectives", "facets", "queries"):
        assert k in P.PLANNER_CONSOLIDATE_PROMPT
    assert "{max_authors}" in P.PLANNER_CONSOLIDATE_PROMPT
