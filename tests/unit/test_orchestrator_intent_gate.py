from shared.events.schemas import ProductQuery

from agents.agent_generator.tools.behavior_analyzer import infer_language
from agents.orchestrator.tools.intent_gate import (
    has_actionable_shopping_query,
    is_conversational_intent,
    is_greeting_only,
    should_run_product_search,
)


def test_is_greeting_only_for_slm() -> None:
    assert is_greeting_only("slm")
    assert is_greeting_only("Salam")
    assert is_greeting_only("labas")


def test_is_not_greeting_for_shopping_message() -> None:
    assert not is_greeting_only("Bghit Samsung phone b 3000 dh")
    assert not is_greeting_only("salam bghit samsung phone")


def test_is_conversational_for_comment_cava() -> None:
    assert is_conversational_intent("commen cava")
    assert is_conversational_intent("comment ca va")
    assert is_conversational_intent("hi how are you")
    assert is_conversational_intent("slm kidayer lbs 3lik")
    assert is_conversational_intent("what service you offer")


def test_should_not_run_product_search_for_greeting() -> None:
    query = ProductQuery()
    assert not should_run_product_search("slm", query)


def test_should_not_run_product_search_for_comment_cava_even_with_ner_product() -> None:
    query = ProductQuery(product="cava")
    assert not should_run_product_search("commen cava", query)


def test_should_run_product_search_for_shopping_query() -> None:
    query = ProductQuery(product="phone", brand="Samsung", budget=3000)
    assert should_run_product_search("Bghit Samsung phone b 3000 dh", query)


def test_has_actionable_shopping_query() -> None:
    assert not has_actionable_shopping_query(ProductQuery())
    assert has_actionable_shopping_query(ProductQuery(product="phone"))
    assert has_actionable_shopping_query(ProductQuery(brand="Samsung"))
    assert has_actionable_shopping_query(ProductQuery(budget=3000))


def test_infer_language_english() -> None:
    assert infer_language("hi how are you and what you do") == "en"
    assert infer_language("what service you offer") == "en"


def test_infer_language_french() -> None:
    assert infer_language("commen cava") == "fr"
    assert infer_language("bonjour je cherche un telephone") == "fr"


def test_infer_language_darija() -> None:
    assert infer_language("slm kidayer lbs 3lik") == "darija"
    assert infer_language("Bghit Samsung phone b 3000 dh") == "darija"
    assert infer_language("chnahoma les services li kadero") == "darija"
    assert infer_language("chno kaydur had lboot") == "darija"
    assert infer_language("slm cv kidayer lbs 3lik") == "darija"


def test_is_conversational_for_darija_help() -> None:
    assert is_conversational_intent("chnahoma les services li kadero")
    assert is_conversational_intent("chno kaydur had lboot")
