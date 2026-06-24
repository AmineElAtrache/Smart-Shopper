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
    r"3tini|mn|f|w|d|b|l|hahuma|tartib|karar|qra|ma3lomat|tafdil|talab|tafasil|"
    r"nata2ij|7sab|dir|khod|wahda|bla|khtar|waqt|b7al"
    r")\b|[3790]",
    re.IGNORECASE,
)

DARIJA_CLOSING_VARIANTS = (
    (
        "Rattabt l-lista 3la taman, thiqa, w l-wjoud b tartib bla ma n-favori wahda. "
        "Qra l-ma3lomat dyal kol wa7da w khod l-karar li 3jbek."
    ),
    (
        "L-lista m-rattba 3la taman, thiqa, w l-wjoud bla tafdil. "
        "Chouf l-ma3lomat w dir l-karar li 3jbek."
    ),
    (
        "Hadi l-ma3lomat li lqit, m-rattbin 3la taman w thiqa bla ma n-pushi wahda. "
        "Qra kol wa7da w khod waqt dyalek f l-khtiar."
    ),
    (
        "M-rattbt l-khityarat 3la taman w thiqa, bla ma n-7eb wahda 3la wahda. "
        "Chouf chno kayn w khod l-karar li y-m3ek."
    ),
    (
        "Tartib dyal l-lista kay7seb taman, thiqa, w l-wjoud, bla tafdil mn jiha dyali. "
        "Qra tafasil kol khityar w khtar li bghiti."
    ),
    (
        "Hadi ghir ma3lomat m-3aradin b tartib, ma kayn la pression w la tawsiya. "
        "Chouf l-ma3lomat w goul li bghiti."
    ),
    (
        "Kol khityar f l-lista 3ndo taman, tqyim, w ma7all dyalo, m-rattbin b tartib neutral. "
        "Khod l-wqt dyalek w khtar li y-3jbek."
    ),
    (
        "L-ma3lomat m-7etota b tartib 3la taman, thiqa, w l-wjoud bla bias. "
        "Dir l-karar dyalek mn ba3d ma t-qra tafasil."
    ),
)


def is_coherent_darija(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if len(cleaned) < 12:
        return False
    if FOREIGN_TOKEN_PATTERN.search(cleaned):
        return False
    return bool(DARIJA_MARKER_PATTERN.search(cleaned))


def is_stale_darija_closing(text: str) -> bool:
    normalized = _normalize_phrase(text)
    if not normalized:
        return True
    first = _normalize_phrase(_first_sentence(text))
    for variant in DARIJA_CLOSING_VARIANTS:
        variant_norm = _normalize_phrase(variant)
        if normalized == variant_norm:
            return True
        if first and first == _normalize_phrase(_first_sentence(variant)):
            return True
    prompt_echo = _normalize_phrase(
        "Rattabt l-lista 3la taman, thiqa, w l-wjoud bla tafdil. Qra l-ma3lomat w khod l-karar li 3jbek."
    )
    hybrid_echo = _normalize_phrase(
        "Rattabt l-lista 3la taman, thiqa, w l-wjoud bla tafdil. Chouf l-ma3lomat w dir l-karar li 3jbek."
    )
    return normalized in {prompt_echo, hybrid_echo}


def build_darija_response(event: DecisionRanked) -> str:
    from agents.agent_generator.agent import build_composed_message

    if not event.products:
        return build_darija_empty_reply()

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
