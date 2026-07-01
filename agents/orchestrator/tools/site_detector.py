"""Fast rule and NER-based detection of user-requested marketplace sites."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from agents.orchestrator.tools.site_registry import (
    PROVIDER_REGISTRY,
    canonical_site_name,
    extract_domains_from_text,
    provider_from_domain,
    validate_site_names,
)
from models.ner.product_vocabulary import detect_site_entities, normalize_key
from shared.events.schemas import EntityType, ExtractedEntity

WORD_BOUNDARY = r"(?<![a-z0-9])"
WORD_END = r"(?![a-z0-9])"

EXPLICIT_PREP_RE = re.compile(
    r"(?:\b(?:mn|min|f|fi|sur|from|gir|via|3la|3lih|on|at|chez)\b)\s+",
    re.IGNORECASE,
)
EXCLUDE_PREP_RE = re.compile(
    r"\b(?:bla|mashi|sans|without|not|except|sauf)\b\s+",
    re.IGNORECASE,
)
MARKETPLACE_HINT_RE = re.compile(
    r"\b(?:site|website|web\s*site|ma7all|mahall|marketplace|market\s*place|"
    r"plateforme|platform|boutique\s*en\s*ligne|online\s*shop)\b",
    re.IGNORECASE,
)


class SiteDetectionSource(StrEnum):
    RULE = "rule"
    NER = "ner"
    LLM = "llm"


@dataclass(frozen=True)
class SiteDetectionResult:
    sites: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()
    explicit: bool = False
    ambiguous: bool = False
    source: SiteDetectionSource | None = None
    confidence: float = 0.0
    hints: tuple[str, ...] = field(default_factory=tuple)


def detect_sites_from_entities(entities: list[ExtractedEntity]) -> list[str]:
    sites: list[str] = []
    for entity in entities:
        if entity.type == EntityType.SITE:
            canonical = canonical_site_name(entity.value)
            if canonical:
                sites.append(canonical)
            continue
        if entity.type != EntityType.INTENT:
            continue
        value = entity.value.lower()
        if value.startswith("site_"):
            canonical = canonical_site_name(value[5:])
            if canonical:
                sites.append(canonical)
        elif entity.attributes.get("category") == "site":
            canonical = canonical_site_name(entity.value)
            if canonical:
                sites.append(canonical)
    return validate_site_names(sites)


def detect_sites_from_rules(
    text: str,
    *,
    product: str | None = None,
) -> SiteDetectionResult:
    normalized = normalize_key(text)
    if not normalized:
        return SiteDetectionResult()

    included: dict[str, float] = {}
    excluded: set[str] = set()

    for domain in extract_domains_from_text(text):
        provider = provider_from_domain(domain)
        if provider:
            included[provider] = max(included.get(provider, 0.0), 0.98)

    product_key = normalize_key(product or "").replace(" ", "_")
    car_context = product_key in {"car", "voiture", "automobile", "tomobile"} or "voiture" in normalized

    alias_entries: list[tuple[str, str, float, bool]] = []
    for name, info in PROVIDER_REGISTRY.items():
        for alias in sorted(info.aliases, key=len, reverse=True):
            base_confidence = 0.72 if info.ambiguous_without_context else 0.88
            alias_entries.append((name, alias, base_confidence, info.ambiguous_without_context))

    for name, alias, base_confidence, ambiguous in alias_entries:
        alias_key = normalize_key(alias)
        if len(alias_key) < 3 and name != "hp":
            continue
        pattern = rf"{WORD_BOUNDARY}{re.escape(alias_key)}{WORD_END}"
        if not re.search(pattern, normalized):
            continue
        if ambiguous and not car_context:
            confidence = 0.62
        else:
            confidence = base_confidence
        if re.search(
            rf"(?:mn|min|f|fi|sur|from|gir|via|3la|3lih|on|at|chez)\s+{re.escape(alias_key)}{WORD_END}",
            normalized,
        ):
            confidence = min(0.99, confidence + 0.08)
        if re.search(
            rf"(?:bla|mashi|sans|without|not|except|sauf)\s+{re.escape(alias_key)}{WORD_END}",
            normalized,
        ):
            excluded.add(name)
            included.pop(name, None)
            continue
        included[name] = max(included.get(name, 0.0), confidence)

    sites = validate_site_names(list(included.keys()))
    excluded_valid = validate_site_names(list(excluded))
    sites = [site for site in sites if site not in excluded_valid]

    if not sites:
        return SiteDetectionResult(
            excluded=tuple(excluded_valid),
            ambiguous=_needs_llm_fallback(text, [], product=product),
        )

    confidence = max(included[site] for site in sites)
    explicit = confidence >= 0.85 or bool(extract_domains_from_text(text))
    ambiguous = _needs_llm_fallback(text, sites, product=product, confidence=confidence)
    return SiteDetectionResult(
        sites=tuple(sites),
        excluded=tuple(excluded_valid),
        explicit=explicit,
        ambiguous=ambiguous,
        source=SiteDetectionSource.RULE,
        confidence=confidence,
    )


def detect_sites_hybrid(
    text: str,
    entities: list[ExtractedEntity],
    *,
    product: str | None = None,
) -> SiteDetectionResult:
    ner_sites = detect_sites_from_entities(entities)
    ner_sites = validate_site_names([*ner_sites, *[entity.value for entity in detect_site_entities(text)]])
    rule_result = detect_sites_from_rules(text, product=product)

    merged = validate_site_names([*ner_sites, *rule_result.sites])
    excluded = validate_site_names([*rule_result.excluded])

    if merged:
        explicit = rule_result.explicit or bool(ner_sites)
        confidence = rule_result.confidence if rule_result.sites else (0.9 if ner_sites else 0.0)
        if ner_sites and not rule_result.sites:
            confidence = max(confidence, 0.9)
        source = SiteDetectionSource.NER if ner_sites and not rule_result.sites else SiteDetectionSource.RULE
        if ner_sites and rule_result.sites:
            source = SiteDetectionSource.RULE
        return SiteDetectionResult(
            sites=tuple(merged),
            excluded=tuple(excluded),
            explicit=explicit,
            ambiguous=_needs_llm_fallback(text, merged, product=product, confidence=confidence),
            source=source,
            confidence=confidence,
        )

    return SiteDetectionResult(
        excluded=tuple(excluded),
        ambiguous=rule_result.ambiguous,
        hints=_marketplace_hints(text),
    )


def _needs_llm_fallback(
    text: str,
    sites: list[str],
    *,
    product: str | None = None,
    confidence: float = 0.0,
) -> bool:
    if sites:
        if len(sites) == 1 and sites[0] == "moteur" and confidence < 0.75:
            product_key = normalize_key(product or "")
            if product_key not in {"car", "voiture", "automobile", "tomobile"}:
                return True
        return False
    return bool(MARKETPLACE_HINT_RE.search(text))


def _marketplace_hints(text: str) -> tuple[str, ...]:
    hints: list[str] = []
    if MARKETPLACE_HINT_RE.search(text):
        hints.append("marketplace_hint")
    return tuple(hints)
