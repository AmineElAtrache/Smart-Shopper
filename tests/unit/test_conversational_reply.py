from agents.orchestrator.tools.conversational_llm import is_valid_conversational_reply
from agents.orchestrator.tools.conversational_reply import build_conversational_reply, is_help_question
from shared.events.schemas import InboundMessage


def test_is_help_question_darija() -> None:
    assert is_help_question("chnahoma les services li kadero")
    assert is_help_question("chno kaydur had lboot")
    assert not is_help_question("slm cv kidayer lbs 3lik")


def test_build_conversational_reply_darija_help() -> None:
    message = InboundMessage(
        request_id="req_1",
        user_id="u1",
        text="chnahoma les services li kadero",
    )
    reply = build_conversational_reply(message)
    assert "Smart Shopper" in reply
    assert "Jumia" in reply
    assert "Hello" not in reply


def test_is_valid_conversational_reply_rejects_bad_darija() -> None:
    assert not is_valid_conversational_reply("Hello! I'm Smart Shopper...", "darija")
    assert not is_valid_conversational_reply("slm 3lik, kifach t-jaweb?", "darija")
    assert is_valid_conversational_reply(
        "Lbas 3lik! Ana Smart Shopper, kan3awen n9leb 3la produits f Jumia w Avito.",
        "darija",
    )
