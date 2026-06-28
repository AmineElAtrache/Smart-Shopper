"""CSV-backed product vocabulary for NER normalization.

The vocabulary is intentionally used as a conservative helper around the model:
- before NER, it rewrites only known aliases/misspellings to cleaner text;
- after NER, it canonicalizes extracted values and enriches missing entities.
"""

from __future__ import annotations

import csv
import os
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from shared.events.schemas import EntityType, ExtractedEntity

try:
    from rapidfuzz import fuzz, process
except ImportError:  # pragma: no cover - rapidfuzz is declared in project deps.
    fuzz = None
    process = None

DEFAULT_VOCAB_PATH = Path(__file__).resolve().parent / "resources" / "product_vocabulary.csv"
DEFAULT_EXTERNAL_VOCAB_PATH = Path(__file__).resolve().parent / "resources" / "external_vocabulary.csv"
VOCAB_PATH_ENV = "SMART_SHOPPER_VOCAB_PATH"
EXTERNAL_VOCAB_PATHS_ENV = "SMART_SHOPPER_EXTERNAL_VOCAB_PATHS"
TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
SPACE_RE = re.compile(r"\s+")
PRE_NER_TYPES = {"brand", "product", "category", "city", "color", "condition", "intent", "site"}
ENTITY_TYPE_BY_VOCAB_TYPE = {
    "brand": EntityType.BRAND,
    "product": EntityType.PRODUCT,
    "category": EntityType.PRODUCT,
    "city": EntityType.CITY,
    "color": EntityType.COLOR,
    "condition": EntityType.QUALITY,
    "intent": EntityType.INTENT,
    "site": EntityType.SITE,
}
FUZZY_MIN_TOKEN_LENGTH = 4
PRE_NER_FUZZY_THRESHOLD = 92
ENTITY_FUZZY_THRESHOLD = 88
INTERNAL_CANONICAL_OVERRIDES = {
    ("brand", "iphone"): "Apple",
    ("product", "iphone"): "phone",
    ("product", "smartphone"): "phone",
    ("product", "pc"): "laptop",
    ("product", "refrigerator"): "fridge",
    ("category", "refrigerator"): "fridge",
}
BLOCKED_BRAND_ALIASES = {
    # "chi" is common Darija filler ("some/a") and appears in many shopping requests.
    "chi",
}


def is_actionable_product_value(value: str | None) -> bool:
    """Reject Darija prepositions and other single-letter junk mis-tagged as products."""
    if not value:
        return False
    normalized = normalize_key(value)
    return len(normalized) > 1
EXTRA_ENTRIES = (
    ("brand", "Samsung", "samsong", "typo", "phone", 0.95, "project alias"),
    ("brand", "Samsung", "samsng", "typo", "phone", 0.95, "project alias"),
    ("brand", "Apple", "iphon", "typo", "phone", 0.95, "project alias"),
    ("product", "Galaxy A15", "galaxi a15", "typo", "phone", 0.92, "project alias"),
    ("product", "phone", "smarfone", "typo", "phone", 0.9, "project alias"),
    ("product", "laptop", "pc", "darija_latin", "laptop", 0.9, "project alias"),
    ("product", "fridge", "telaja", "darija_latin", "home_appliance", 0.9, "project alias"),
    ("product", "air fryer", "airfryer", "en", "home_appliance", 0.95, "compact spelling"),
    ("product", "air fryer", "air fryer", "en", "home_appliance", 0.95, "kitchen appliance"),
    ("product", "air fryer", "friteuse sans huile", "fr", "home_appliance", 0.94, "french appliance phrase"),
    ("product", "air fryer", "friteuse air fryer", "fr", "home_appliance", 0.92, "mixed french english phrase"),
    ("product", "air fryer", "قلاية هوائية", "ar", "home_appliance", 0.86, "arabic appliance phrase"),
    ("product", "tv", "tele", "fr", "home_appliance", 0.94, "colloquial french for TV"),
    ("product", "washing_machine", "washing_machine", "en", "home_appliance", 0.93, "underscore token"),
    ("color", "black", "kehla", "darija_latin", "general", 0.9, "project alias"),
    ("color", "black", "k7la", "darija_latin", "general", 0.9, "project alias"),
)


@dataclass(frozen=True)
class VocabularyEntry:
    type: str
    canonical: str
    alias: str
    language: str
    category: str
    confidence: float
    notes: str = ""

    @property
    def alias_key(self) -> str:
        return normalize_key(self.alias)

    @property
    def canonical_key(self) -> str:
        return normalize_key(self.canonical)

    @property
    def normalized_canonical(self) -> str:
        return INTERNAL_CANONICAL_OVERRIDES.get((self.type, self.canonical_key), self.canonical)

    @property
    def normalized_canonical_key(self) -> str:
        return normalize_key(self.normalized_canonical)

    @property
    def entity_type(self) -> EntityType | None:
        return ENTITY_TYPE_BY_VOCAB_TYPE.get(self.type)


def normalize_key(value: str | None) -> str:
    if not value:
        return ""
    text = "".join(
        character
        for character in unicodedata.normalize("NFKD", value.lower())
        if not unicodedata.combining(character)
    )
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return SPACE_RE.sub(" ", text).strip()


def _split_vocab_paths(raw_value: str | None) -> list[Path]:
    if raw_value is None:
        return []
    return [Path(value.strip()) for value in re.split(r"[;,]", raw_value) if value.strip()]


def _configured_vocabulary_paths() -> list[Path]:
    paths = [Path(os.getenv(VOCAB_PATH_ENV, str(DEFAULT_VOCAB_PATH)))]
    external_raw = os.getenv(EXTERNAL_VOCAB_PATHS_ENV)
    external_paths = _split_vocab_paths(external_raw)
    if external_raw is None:
        external_paths = [DEFAULT_EXTERNAL_VOCAB_PATH]
    paths.extend(external_paths)
    return paths


def _read_vocabulary_file(path: Path) -> list[VocabularyEntry]:
    if not path.exists():
        return []

    entries: list[VocabularyEntry] = []
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        for row in csv.DictReader(csv_file):
            alias = (row.get("alias") or "").strip()
            canonical = (row.get("canonical") or "").strip()
            vocab_type = (row.get("type") or "").strip().lower()
            if not alias or not canonical or vocab_type not in ENTITY_TYPE_BY_VOCAB_TYPE:
                continue
            try:
                confidence = float(row.get("confidence") or 0.8)
            except ValueError:
                confidence = 0.8
            entries.append(
                VocabularyEntry(
                    type=vocab_type,
                    canonical=canonical,
                    alias=alias,
                    language=(row.get("language") or "").strip(),
                    category=(row.get("category") or "").strip(),
                    confidence=max(0.0, min(confidence, 1.0)),
                    notes=(row.get("notes") or "").strip(),
                )
            )
    return entries


@lru_cache(maxsize=1)
def load_vocabulary() -> tuple[VocabularyEntry, ...]:
    entries: list[VocabularyEntry] = []
    for path in _configured_vocabulary_paths():
        entries.extend(_read_vocabulary_file(path))

    entries.extend(
        VocabularyEntry(
            type=item[0],
            canonical=item[1],
            alias=item[2],
            language=item[3],
            category=item[4],
            confidence=item[5],
            notes=item[6],
        )
        for item in EXTRA_ENTRIES
    )
    return tuple(entries)


@lru_cache(maxsize=1)
def _exact_aliases() -> dict[str, VocabularyEntry]:
    aliases: dict[str, VocabularyEntry] = {}
    for entry in load_vocabulary():
        key = entry.alias_key
        if not key:
            continue
        if entry.type == "brand" and key in BLOCKED_BRAND_ALIASES:
            continue
        current = aliases.get(key)
        if current is None or entry.confidence > current.confidence:
            aliases[key] = entry
    return aliases


@lru_cache(maxsize=1)
def _aliases_by_type() -> dict[EntityType, dict[str, VocabularyEntry]]:
    grouped: dict[EntityType, dict[str, VocabularyEntry]] = {}
    for alias, entry in _exact_aliases().items():
        entity_type = entry.entity_type
        if entity_type is None:
            continue
        grouped.setdefault(entity_type, {})[alias] = entry
    return grouped


@lru_cache(maxsize=1)
def _fuzzy_choices_by_type() -> dict[EntityType, list[str]]:
    return {entity_type: sorted(aliases) for entity_type, aliases in _aliases_by_type().items()}


@lru_cache(maxsize=1)
def city_aliases() -> dict[str, str]:
    """Build alias -> canonical city map from vocabulary CSV (single source of truth)."""
    aliases: dict[str, str] = {}
    confidence_by_key: dict[str, float] = {}

    for entry in load_vocabulary():
        if entry.type != "city":
            continue
        canonical = entry.canonical_key
        if not canonical:
            continue

        for alias_key in {entry.alias_key, canonical}:
            if not alias_key:
                continue
            current_confidence = confidence_by_key.get(alias_key, -1.0)
            if alias_key not in aliases or entry.confidence > current_confidence:
                aliases[alias_key] = canonical
                confidence_by_key[alias_key] = entry.confidence

    return aliases


def _is_pre_ner_safe(entry: VocabularyEntry) -> bool:
    return entry.type in PRE_NER_TYPES and entry.language != "brand_model"


def is_exact_vocabulary_alias(value: str) -> bool:
    """Return True when the token is a known vocabulary alias (exact match)."""
    key = normalize_key(value)
    return bool(key) and key in _exact_aliases()


def normalize_text(text: str) -> str:
    """Rewrite known aliases in free text before NER inference."""
    normalized = normalize_key(text)
    if not normalized:
        return ""

    for alias, entry in sorted(_exact_aliases().items(), key=lambda item: len(item[0]), reverse=True):
        if not _is_pre_ner_safe(entry) or entry.confidence < 0.84:
            continue
        if len(alias) < 3 and alias != entry.canonical_key:
            continue
        replacement = entry.normalized_canonical_key
        normalized = re.sub(rf"(?<!\w){re.escape(alias)}(?!\w)", replacement, normalized)

    tokens = [correct_token(token) for token in TOKEN_RE.findall(normalized)]
    return " ".join(tokens)


def correct_token(token: str) -> str:
    key = normalize_key(token)
    if not key or key.isdigit():
        return token

    exact = _exact_aliases().get(key)
    if (
        exact is not None
        and _is_pre_ner_safe(exact)
        and exact.confidence >= 0.84
        and (len(key) >= 3 or key == exact.canonical_key)
    ):
        return exact.normalized_canonical_key

    if len(key) < FUZZY_MIN_TOKEN_LENGTH:
        return key

    choices = [alias for alias, entry in _exact_aliases().items() if _is_pre_ner_safe(entry)]
    match = _fuzzy_match(key, choices, threshold=PRE_NER_FUZZY_THRESHOLD)
    if match is None:
        return key
    return _exact_aliases()[match].normalized_canonical_key


def canonicalize_entity_value(entity_type: EntityType, value: str) -> str | None:
    key = normalize_key(value)
    if not key:
        return None

    aliases = _aliases_by_type().get(entity_type, {})
    exact = aliases.get(key)
    if exact is not None:
        return exact.normalized_canonical

    if len(key) >= FUZZY_MIN_TOKEN_LENGTH:
        match = _fuzzy_match(
            key,
            _fuzzy_choices_by_type().get(entity_type, []),
            threshold=ENTITY_FUZZY_THRESHOLD,
        )
        if match is not None:
            return aliases[match].normalized_canonical

    return None


def detect_entities(text: str, *, min_confidence: float = 0.78) -> list[ExtractedEntity]:
    """Detect vocabulary-backed entities from normalized text."""
    normalized = normalize_key(text)
    if not normalized:
        return []

    entities: list[ExtractedEntity] = []
    seen: set[EntityType] = set()
    for alias, entry in sorted(_exact_aliases().items(), key=lambda item: len(item[0]), reverse=True):
        entity_type = entry.entity_type
        if entity_type is None or entity_type in seen or entry.confidence < min_confidence:
            continue
        if entry.type == "brand" and entry.language == "brand_model":
            continue
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized):
            attributes = {"source": "product_vocabulary"}
            if entry.category:
                attributes["category"] = entry.category
            entities.append(
                ExtractedEntity(
                    type=entity_type,
                    value=entry.normalized_canonical,
                    confidence=entry.confidence,
                    attributes=attributes,
                )
            )
            seen.add(entity_type)
    return entities


def detect_site_entities(text: str, *, min_confidence: float = 0.82) -> list[ExtractedEntity]:
    """Detect multiple marketplace site mentions from vocabulary aliases."""
    normalized = normalize_key(text)
    if not normalized:
        return []

    entities: list[ExtractedEntity] = []
    seen_sites: set[str] = set()
    for alias, entry in sorted(_exact_aliases().items(), key=lambda item: len(item[0]), reverse=True):
        if entry.confidence < min_confidence:
            continue
        is_site = entry.category == "site" or entry.canonical_key.startswith("site_")
        if not is_site:
            continue
        if not re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized):
            continue
        site_value = (
            entry.canonical_key[5:]
            if entry.canonical_key.startswith("site_")
            else entry.normalized_canonical_key
        )
        if site_value in seen_sites:
            continue
        seen_sites.add(site_value)
        attributes = {"source": "product_vocabulary", "category": "site"}
        entities.append(
            ExtractedEntity(
                type=EntityType.SITE,
                value=site_value,
                confidence=entry.confidence,
                attributes=attributes,
            )
        )
    return entities


def _fuzzy_match(token: str, choices: list[str], *, threshold: int) -> str | None:
    if not choices:
        return None
    if process is not None and fuzz is not None:
        result = process.extractOne(token, choices, scorer=fuzz.WRatio, score_cutoff=threshold)
        return str(result[0]) if result else None
    return None
