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
VOCAB_PATH_ENV = "SMART_SHOPPER_VOCAB_PATH"
TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
SPACE_RE = re.compile(r"\s+")
PRE_NER_TYPES = {"brand", "product", "category", "color", "condition", "intent"}
ENTITY_TYPE_BY_VOCAB_TYPE = {
    "brand": EntityType.BRAND,
    "product": EntityType.PRODUCT,
    "category": EntityType.PRODUCT,
    "color": EntityType.COLOR,
    "condition": EntityType.QUALITY,
    "intent": EntityType.INTENT,
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
}
EXTRA_ENTRIES = (
    ("brand", "Samsung", "samsong", "typo", "phone", 0.95, "project alias"),
    ("brand", "Samsung", "samsng", "typo", "phone", 0.95, "project alias"),
    ("brand", "Apple", "iphon", "typo", "phone", 0.95, "project alias"),
    ("product", "Galaxy A15", "galaxi a15", "typo", "phone", 0.92, "project alias"),
    ("product", "phone", "smarfone", "typo", "phone", 0.9, "project alias"),
    ("product", "laptop", "pc", "darija_latin", "laptop", 0.9, "project alias"),
    ("product", "fridge", "telaja", "darija_latin", "home_appliance", 0.9, "project alias"),
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


@lru_cache(maxsize=1)
def load_vocabulary() -> tuple[VocabularyEntry, ...]:
    path = Path(os.getenv(VOCAB_PATH_ENV, str(DEFAULT_VOCAB_PATH)))
    if not path.exists():
        return ()

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


def _is_pre_ner_safe(entry: VocabularyEntry) -> bool:
    return entry.type in PRE_NER_TYPES and entry.language != "brand_model"


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


def _fuzzy_match(token: str, choices: list[str], *, threshold: int) -> str | None:
    if not choices:
        return None
    if process is not None and fuzz is not None:
        result = process.extractOne(token, choices, scorer=fuzz.WRatio, score_cutoff=threshold)
        return str(result[0]) if result else None
    return None
