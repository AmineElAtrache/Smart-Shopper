"""Localized intro and closing variants for English, French, and Arabic."""

from __future__ import annotations

import hashlib

from shared.events.schemas import DecisionRanked, RankedProduct

EN_CLOSING_VARIANTS = (
    "Listed by score using price, trust, and availability. Review the details and decide what works for you.",
    "Results are ordered by score, price, trust, and availability. Take a look and choose when you are ready.",
    "Each option shows price, source, and score. Check the details and go with what suits you.",
    "Sorted by overall score from price, trust, and availability. Read through and make your call.",
    "The list reflects price, trust, and availability in the ranking. See what matches your needs.",
    "Prices, sources, and scores are listed below. Compare them and decide at your pace.",
    "The ranking weighs price, trust, and availability. Look at the details and choose what you prefer.",
    "Here is the breakdown by price, trust, and availability. Compare and pick what fits.",
)

FR_CLOSING_VARIANTS = (
    "Classee par score selon le prix, la confiance et la disponibilite. Compare les details et choisis ce qui te convient.",
    "Liste ordonnee par score, prix, confiance et disponibilite. Parcours les options et fais ton choix.",
    "Chaque option montre le prix, la source et la note. Regarde les details et prends ta decision.",
    "Tri par score en tenant compte du prix, de la confiance et de la disponibilite. A toi de voir ce qui te va.",
    "Les resultats sont classes par note, prix et confiance. Compare et choisis quand tu es pret.",
    "Voici le classement selon le prix, la confiance et la disponibilite. Lis les details et decide.",
    "Prix, source et score pour chaque option. Parcours et choisis ce qui te correspond.",
    "Le tri repose sur le prix, la confiance et la disponibilite. Regarde et decide a ton rythme.",
)

AR_CLOSING_VARIANTS = (
    "مرتبة حسب السعر والثقة والتوفر. راجع التفاصيل واختر ما يناسبك.",
    "القائمة مرتبة حسب السعر والثقة والتوفر. اطلع على التفاصيل وقرر ما يناسبك.",
    "كل خيار يظهر السعر والمصدر والتقييم. راجع التفاصيل واختر ما يناسبك.",
    "الترتيب يعتمد على السعر والثقة والتوفر. قارن الخيارات وقرر.",
)

EN_INTRO_VARIANTS = (
    "Here are {count} option{suffix} from your search.",
    "I found {count} option{suffix} for your search.",
    "Based on your request, here are {count} option{suffix}.",
    "Your search returned {count} option{suffix}.",
)

FR_INTRO_VARIANTS = (
    "Voici {count} option{suffix} pour ta recherche.",
    "J'ai trouve {count} option{suffix} pour toi.",
    "Pour ta recherche, voici {count} option{suffix}.",
    "Ta recherche a donne {count} option{suffix}.",
)

AR_INTRO_VARIANTS = (
    "إليك {count} خيارات من بحثك.",
    "وجدت {count} خيارات لطلبك.",
    "بناءً على طلبك، إليك {count} خيارات.",
)

EN_HEADER_VARIANTS = ("Details:", "Options:", "Here are the details:", "Product list:")
FR_HEADER_VARIANTS = ("Details:", "Options:", "Voici les details:", "Liste des produits:")
AR_HEADER_VARIANTS = ("التفاصيل:", "الخيارات:", "إليك التفاصيل:")


def seed_for_event(event: DecisionRanked) -> str:
    return (event.user_text or event.request_id or "response").strip()


def localized_closing(language: str, *, seed: str = "") -> str:
    variants = {
        "fr": FR_CLOSING_VARIANTS,
        "ar": AR_CLOSING_VARIANTS,
        "en": EN_CLOSING_VARIANTS,
    }.get(language, EN_CLOSING_VARIANTS)
    return variants[_variant_index(seed, len(variants), salt="closing")]


def localized_intro(language: str, count: int, *, seed: str = "") -> str:
    suffix = "s" if count != 1 else ""
    if language == "fr":
        fr_suffix = "s" if count != 1 else ""
        template = FR_INTRO_VARIANTS[_variant_index(seed, len(FR_INTRO_VARIANTS), salt="intro")]
        return template.format(count=count, suffix=fr_suffix)
    if language == "ar":
        template = AR_INTRO_VARIANTS[_variant_index(seed, len(AR_INTRO_VARIANTS), salt="intro")]
        return template.format(count=count, suffix=suffix)
    template = EN_INTRO_VARIANTS[_variant_index(seed, len(EN_INTRO_VARIANTS), salt="intro")]
    return template.format(count=count, suffix=suffix)


def localized_product_header(language: str, *, seed: str = "") -> str:
    variants = {
        "fr": FR_HEADER_VARIANTS,
        "ar": AR_HEADER_VARIANTS,
        "en": EN_HEADER_VARIANTS,
    }.get(language, EN_HEADER_VARIANTS)
    return variants[_variant_index(seed, len(variants), salt="header")]


def build_standard_response(event: DecisionRanked, language: str) -> str:
    from agents.agent_generator.agent import build_composed_message

    if not event.products:
        if language == "fr":
            return (
                "Salut! Dis-moi ce que tu cherches, ton budget, "
                "et ta ville si tu veux, et je lance la recherche."
            )
        if language == "ar":
            return "مرحباً! أخبرني بما تبحث عنه وميزانيتك ومدينتك إن أردت، وسأبدأ البحث."
        return (
            "Hi, I could not find product options yet. "
            "Send me what you are looking for and your budget, and I will search for options."
        )

    seed = seed_for_event(event)
    count = min(3, len(event.products))
    return build_composed_message(
        event.products,
        intro=localized_intro(language, count, seed=seed),
        product_header=localized_product_header(language, seed=seed),
        best_reason=localized_closing(language, seed=seed),
        product_style="labeled",
    )


def _variant_index(seed: str, count: int, *, salt: str = "") -> int:
    if count <= 1:
        return 0
    digest = hashlib.sha256(f"{seed}:{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % count
