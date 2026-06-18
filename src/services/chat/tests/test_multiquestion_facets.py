from src.services.chat.agents.definition_gaps import multi_question_split
from src.services.chat.agents.definition_gaps import concepts_from_asks, _MAX_GAPS
from src.services.chat.agents.definition_gaps import augment_concepts_and_facets
from src.services.chat.agents.definition_gaps import detect_definition_gaps


def test_split_three_questions():
    q = "What is stationarity? What are its versions? What is a unit root?"
    assert multi_question_split(q) == [
        "What is stationarity?",
        "What are its versions?",
        "What is a unit root?",
    ]


def test_single_question_returns_itself():
    assert multi_question_split("What is a unit root?") == ["What is a unit root?"]


def test_no_question_mark_returns_itself():
    assert multi_question_split("Explain stationarity.") == ["Explain stationarity."]


def test_caps_at_five():
    q = " ".join(f"Q{i}?" for i in range(8))
    assert len(multi_question_split(q)) <= 5


def test_concepts_from_asks_strips_scaffolding():
    asks = ["What is stationarity?", "What is a unit root?"]
    got = concepts_from_asks(asks)
    assert "stationarity" in got
    assert "unit root" in got


def test_max_gaps_fits_four_forms():
    assert _MAX_GAPS >= 5


def test_augment_unions_asks_first():
    query = "What is stationarity? What are its versions? What is a unit root?"
    concepts, facets = augment_concepts_and_facets(query, ["stationarity"], ["stationarity"])
    assert concepts[0] == "stationarity"
    assert "unit root" in concepts
    assert "What is a unit root?" in facets


def test_augment_single_question_noop_ish():
    concepts, facets = augment_concepts_and_facets("What is a unit root?", ["unit root"], ["unit root"])
    assert "unit root" in concepts


def test_stationarity_prompt_surfaces_all_required_forms():
    query = "What is stationarity? What are its versions? What is a unit root?"
    concepts, _facets = augment_concepts_and_facets(query, ["stationarity"], ["stationarity"])
    gaps = {g.norm for g in detect_definition_gaps(concepts, query, [])}
    assert "strict stationarity" in gaps
    assert "weak stationarity" in gaps
    assert "unit root" in gaps