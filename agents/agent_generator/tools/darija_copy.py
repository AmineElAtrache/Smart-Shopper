"""Curated Moroccan Darija (Arabizi) copy for coherent shopping replies."""

from __future__ import annotations

import hashlib
import re

from shared.events.schemas import DecisionRanked

DARIJA_LABELS = {
    "price": "Taman",
    "source": "Ma7all",
    "score": "Tqyim",
    "link": "Lien",
}

FOREIGN_TOKEN_PATTERN = re.compile(
    r"\b("
    r"verify|seller|delivery|availability|stock|best|choice|options|open|the|"
    r"option|meilleur|commence|verifie|vendeur|pour|avec|vous|j'ai|l'option|"
    r"found|ranked|value|trust|quality|start|check|before|buying|link|phone|budget|"
    r"recommend|top|buy"
    r")\b",
    re.IGNORECASE,
)

DARIJA_MARKER_PATTERN = re.compile(
    r"\b("
    r"l9it|bghit|kayna|chouf|qbel|taman|khityar|khityarat|rattab|rattabt|3la|"
    r"t2akked|lbayi3|wjoud|thiqa|qima|daba|afak|chno|wach|kayn|bghiti|n9leb|"
    r"3tini|mn|f|w|d|b|l|hahuma|tartib|karar|qra|ma3lomat|talab|tafasil|"
    r"nata2ij|7sab|dir|khod|wahda|bla|khtar|waqt|b7al"
    r")\b|[3790]",
    re.IGNORECASE,
)

DARIJA_CLOSING_VARIANTS = (
    (
        "L-lista m-rattba 3la taman, thiqa, w l-wjoud. "
        "Qra tafasil kol khityar w khtar li bghiti."
    ),
    (
        "Tartib kay7seb taman, thiqa, w l-wjoud dyal kol wa7da. "
        "Chouf l-ma3lomat w dir l-karar dyalek."
    ),
    (
        "Kol khityar 3ndo taman, tqyim, w ma7all dyalo. "
        "Khod l-wqt dyalek w chouf li y-m3ek."
    ),
    (
        "Hadi tafasil li lqit, m-7etotin 3la taman w thiqa. "
        "Goul li bghiti mn ba3d ma t-qra."
    ),
    (
        "L-ma3lomat lta7t m-rattba 3la taman, thiqa, w l-wjoud. "
        "Chouf kol wa7da w khod l-karar li 3jbek."
    ),
    (
        "Dakchi li lqit m-rattab 3la taman w thiqa. "
        "Qra w khtar li bghiti."
    ),
    (
        "Hahuma kol khityar b taman, tqyim, w ma7all dyalo. "
        "Chouf tafasil w khtar li bghiti."
    ),
    (
        "Mn ba3d ma t-chouf taman w tqyim, khod l-karar li y-m3ek."
    ),
)


def is_coherent_darija(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if len(cleaned) < 12:
        return False
    if FOREIGN_TOKEN_PATTERN.search(cleaned):
        return False
    return bool(DARIJA_MARKER_PATTERN.search(cleaned))


LEGACY_STALE_DARIJA_CLOSINGS = (
    "Rattabt l-lista 3la taman, thiqa, w l-wjoud bla tafdil. Qra l-ma3lomat w khod l-karar li 3jbek.",
    "Rattabt l-lista 3la taman, thiqa, w l-wjoud bla tafdil. Chouf l-ma3lomat w dir l-karar li 3jbek.",
    "Tartib dyal l-lista kay7seb taman w thiqa bla tafdil. Khtar li bghiti mn ba3d ma t-qra.",
    "L-lista m-rattba 3la taman, thiqa, w l-wjoud bla tafdil. Chouf l-ma3lomat w dir l-karar li 3jbek.",
)


def is_stale_darija_closing(text: str) -> bool:
    normalized = _normalize_phrase(text)
    if not normalized:
        return True
    legacy = {_normalize_phrase(phrase) for phrase in LEGACY_STALE_DARIJA_CLOSINGS}
    if normalized in legacy:
        return True
    first = _normalize_phrase(_first_sentence(text))
    legacy_first = {_normalize_phrase(_first_sentence(phrase)) for phrase in LEGACY_STALE_DARIJA_CLOSINGS}
    return bool(first and first in legacy_first)


def build_darija_no_results_reply(event: DecisionRanked) -> str:
    query = event.query
    if query and (query.brand or query.product or query.budget is not None):
        label = _search_label(query)
        budget_part = ""
        if query.budget is not None:
            currency = query.currency or "MAD"
            budget_part = f" f {query.budget:g} {currency}"
        return (
            f"Ma lqit 7ta khityar li y-match {label}{budget_part}. "
            "Jarrab tzid l-mizaniya chwiya, badel l-model, wla 3tini mdina."
        )
    return build_darija_empty_reply()


def build_darija_response(event: DecisionRanked) -> str:
    from agents.agent_generator.agent import build_composed_message

    if not event.products:
        return build_darija_no_results_reply(event)

    seed = seed_for_event(event)
    count = min(3, len(event.products))
    product_hint = _product_hint(event)
    return build_composed_message(
        event.products,
        intro=darija_intro(count, product_hint, seed=seed),
        product_header=darija_product_header(seed=seed),
        best_reason=darija_closing(seed=seed),
        labels=DARIJA_LABELS,
        product_style="darija",
    )


def build_darija_empty_reply() -> str:
    return (
        "Salam! Chno bghiti n9leb lik 3lih? "
        "3tini chno bghiti, ch7al l-mizaniya dyalek, w ila bghiti l-mdina."
    )


def darija_intro(count: int, product_hint: str | None = None, *, seed: str = "") -> str:
    suffix = "at" if count != 1 else "a"
    brand = product_hint or "had l-blad"
    variants = [
        f"Hahuma {count} khityar{suffix} li lqit lik f {brand}.",
        f"L9it lik {count} khityar{suffix} f {brand}, hahuma tafasil.",
        f"3la 7sab talab dyalek, hahuma {count} khityar{suffix} f {brand}.",
        f"Hahuma {count} nata2ij 3la {brand} li qderit n-wrihalk.",
        f"Kan9leb 3lik {count} khityar{suffix} f {brand}, hahuma l-ma3lomat.",
        f"Wakha, hahuma {count} khityar{suffix} li lqit f {brand}.",
    ]
    if not product_hint:
        variants = [
            f"Hahuma {count} khityar{suffix} li lqit lik.",
            f"L9it lik {count} khityar{suffix}, hahuma tafasil.",
            f"3la 7sab talab dyalek, hahuma {count} khityar{suffix}.",
        ]
    return variants[_variant_index(seed, len(variants), salt="intro")]


def darija_product_header(*, seed: str = "") -> str:
    variants = [
        "Tafasil dyal kol khityar:",
        "Hahuma l-ma3lomat:",
        "Shuf l-ma3lomat hna:",
        "Dakchi li lqit lik:",
        "Hadi hiya tafasil:",
    ]
    return variants[_variant_index(seed, len(variants), salt="header")]


def darija_closing(*, seed: str = "") -> str:
    return DARIJA_CLOSING_VARIANTS[
        _variant_index(seed, len(DARIJA_CLOSING_VARIANTS), salt="closing")
    ]


def seed_for_event(event: DecisionRanked) -> str:
    return (event.user_text or event.request_id or "darija").strip()


def _variant_index(seed: str, count: int, *, salt: str = "") -> int:
    if count <= 1:
        return 0
    digest = hashlib.sha256(f"{seed}:{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % count


def _first_sentence(text: str) -> str:
    for separator in (". ", "! ", "? ", "؟ "):
        if separator in text:
            return text.split(separator, 1)[0]
    return text


def _normalize_phrase(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower().rstrip(".!?؟…"))


def _search_label(query) -> str:
    parts = [query.brand, _darija_product_label(query.product) or query.product]
    label = " ".join(part for part in parts if part).strip()
    return label or "had talab"


def _product_hint(event: DecisionRanked) -> str | None:
    if event.query is None:
        return None
    if event.query.brand:
        return event.query.brand
    return _darija_product_label(event.query.product)


def _darija_product_label(product: str | None) -> str | None:
    if not product:
        return None
    mapping = {
        "phone": "tilifun",
        "laptop": "portable",
        "chair": "kursi",
        "shoes": "snniitra",
    }
    return mapping.get(product.lower(), product)
