"""Localized conversational replies when no product search is needed."""

from __future__ import annotations

import re

from agents.agent_generator.tools.behavior_analyzer import infer_language
from shared.events.schemas import InboundMessage

_HELP_INTENT = re.compile(
    r"(?:"
    r"\bservice\b|\bservices\b|"
    r"\bkaydur\b|\bkaydir\b|\bkader\b|\bkadero\b|\bkatdir\b|"
    r"\bchno kay\b|\bchnahoma\b|\bchnahuma\b|\blboot\b|\bboot\b|"
    r"\bwhat do you\b|\bwhat you do\b|\bwhat service\b|\bwhat can you\b"
    r")",
    re.IGNORECASE,
)


def is_help_question(text: str) -> bool:
    return bool(_HELP_INTENT.search(text or ""))


def build_conversational_reply(message: InboundMessage) -> str:
    text = message.text or ""
    language = infer_language(text)
    help_question = is_help_question(text)

    if language == "darija":
        if help_question:
            return (
                "Ana Smart Shopper, assistant dyal shopping f l-Maghrib. "
                "Kan9leb lik 3la produits f Jumia, Avito, Electroplanet, Marjane w IKEA. "
                "Goul liya chno bghiti w ch7al l-mizaniya dyalek."
            )
        return (
            "Salam! Lbas 3lik? Ana hna bach n3awnek t9leb 3la produits. "
            "Goul liya chno bghiti w ch7al l-mizaniya dyalek."
        )
    if language == "fr":
        if help_question:
            return (
                "Je suis Smart Shopper, ton assistant shopping au Maroc. "
                "Je t'aide à chercher et comparer des produits sur Jumia, Avito, "
                "Electroplanet, Marjane et IKEA. Dis-moi ce que tu cherches et ton budget."
            )
        return (
            "Salut! Dis-moi ce que tu cherches, ton budget, "
            "et ta ville si tu veux, et je lance la recherche."
        )
    if language == "ar":
        if help_question:
            return (
                "أنا Smart Shopper، مساعد تسوق مغربي. "
                "أساعدك في البحث عن المنتجات ومقارنتها في Jumia وAvito ومتاجر مغربية أخرى. "
                "أخبرني بما تبحث عنه وميزانيتك."
            )
        return "مرحباً! أخبرني بما تبحث عنه وميزانيتك ومدينتك إن أردت، وسأبدأ البحث."
    if help_question:
        return (
            "I'm Smart Shopper, your Moroccan shopping assistant. "
            "I help you search and compare products on Jumia, Avito, Electroplanet, Marjane, and IKEA. "
            "Tell me what you want and your budget."
        )
    return (
        "Hi! Tell me what you are looking for, your budget, "
        "and your city if helpful, and I will search for options."
    )
