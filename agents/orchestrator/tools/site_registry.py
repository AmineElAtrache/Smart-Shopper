"""Registered scrape providers and alias/domain normalization."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from agents.orchestrator.tools.provider_router import DEFAULT_SITES

DOMAIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"([a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:ma|com|net|org|store))"
    r"(?:/[^\s]*)?",
    re.IGNORECASE,
)

EXTRA_ALIASES: dict[str, set[str]] = {
    "jumia": {"jumia ma", "jumia.ma"},
    "avito": {"avito ma", "avito.ma"},
    "electroplanet": {"electro planet", "electroplanet.ma"},
    "electrosalam": {"electro salam", "electrosalam.ma"},
    "mubawab": {"mubawab ma", "mubawab.ma"},
    "decathlon": {"decathlon ma", "decathlon.ma"},
    "ikea": {"ikea ma", "ikea.ma"},
    "marjane": {"marjane ma", "marjane.ma"},
    "defacto": {"de facto", "defacto.ma"},
    "biougnach": {"biougnach.ma"},
    "ultrapc": {"ultra pc", "ultrapc.ma"},
    "mymarket": {"my market", "mymarket.ma"},
    "mafiawaystore": {"mafia way", "mafiawaystore.com"},
    "moteur": {"moteur ma", "moteur.ma"},
    "palmarosa": {"palmarosa.ma"},
    "bringo": {"bringo.ma"},
    "planetsport": {"planet sport", "planetsport.ma"},
}


@dataclass(frozen=True)
class ProviderSiteInfo:
    name: str
    aliases: frozenset[str] = field(default_factory=frozenset)
    domains: frozenset[str] = field(default_factory=frozenset)
    ambiguous_without_context: bool = False


def _build_registry() -> dict[str, ProviderSiteInfo]:
    registry: dict[str, ProviderSiteInfo] = {}
    for name in DEFAULT_SITES:
        aliases = {name, name.replace("_", " ")}
        aliases.update(EXTRA_ALIASES.get(name, set()))
        domains = {f"{name}.ma", f"www.{name}.ma"}
        if name == "mafiawaystore":
            domains = {"mafiawaystore.com", "www.mafiawaystore.com"}
        registry[name] = ProviderSiteInfo(
            name=name,
            aliases=frozenset(aliases),
            domains=frozenset(domains),
            ambiguous_without_context=name == "moteur",
        )
    return registry


PROVIDER_REGISTRY: dict[str, ProviderSiteInfo] = _build_registry()
REGISTERED_SITE_NAMES: frozenset[str] = frozenset(DEFAULT_SITES)


def normalize_site_token(value: str | None) -> str:
    if not value:
        return ""
    token = re.sub(r"[_\W]+", " ", value.lower()).strip()
    if token.startswith("site "):
        token = token[5:].strip()
    if token.startswith("site_"):
        token = token[5:].strip()
    return token.replace(" ", "_")


def canonical_site_name(value: str | None) -> str | None:
    if not value:
        return None
    if "." in value:
        domain_match = provider_from_domain(value.lower().removeprefix("http://").removeprefix("https://"))
        if domain_match:
            return domain_match
    key = normalize_site_token(value)
    if not key:
        return None
    if key in REGISTERED_SITE_NAMES:
        return key
    spaced = key.replace("_", " ")
    for name, info in PROVIDER_REGISTRY.items():
        if spaced in info.aliases or key in info.aliases:
            return name
    return None


def validate_site_names(sites: list[str]) -> list[str]:
    """Keep only registered providers, preserving first-seen order."""
    validated: list[str] = []
    seen: set[str] = set()
    for site in sites:
        canonical = canonical_site_name(site)
        if canonical and canonical not in seen:
            validated.append(canonical)
            seen.add(canonical)
    return validated


def provider_from_domain(domain: str) -> str | None:
    lowered = domain.lower().removeprefix("www.")
    for name, info in PROVIDER_REGISTRY.items():
        if lowered in info.domains or lowered.endswith(f".{name}.ma") or lowered == f"{name}.ma":
            return name
        for known_domain in info.domains:
            if lowered == known_domain.removeprefix("www."):
                return name
    host_root = lowered.split(".", 1)[0]
    return canonical_site_name(host_root)


def extract_domains_from_text(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in DOMAIN_RE.finditer(text.lower()):
        domain = match.group(1).removeprefix("www.")
        if domain not in seen:
            found.append(domain)
            seen.add(domain)
    for token in text.split():
        parsed = urlparse(token if "://" in token else f"https://{token}")
        if parsed.hostname:
            domain = parsed.hostname.lower().removeprefix("www.")
            if domain not in seen:
                found.append(domain)
                seen.add(domain)
    return found
