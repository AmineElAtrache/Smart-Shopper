"""Convert Open Food/Beauty/Products Facts exports into Smart Shopper vocabulary.

The Open Facts exports are large TSV/CSV files. This script extracts only safe,
useful product/category/brand aliases and writes the same schema used by
``models/ner/resources/product_vocabulary.csv``. Inputs can be local files or
official Open Facts export URLs. Remote gzip exports are streamed, so raw files
are not stored in the repository.

Example:
  python -m scripts.import_open_facts_vocabulary `
      --input https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz `
      --input https://static.openbeautyfacts.org/data/en.openbeautyfacts.org.products.csv.gz `
      --country morocco --country maroc --country france `
      --max-rows 200000 `
      --output models/ner/resources/external_vocabulary.csv
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, TextIO
from urllib.parse import urlparse
from urllib.request import Request, urlopen

VOCAB_COLUMNS = ["type", "canonical", "alias", "language", "category", "confidence", "notes"]
DEFAULT_OUTPUT_PATH = Path("models/ner/resources/external_vocabulary.csv")
SPACE_RE = re.compile(r"\s+")
SPLIT_RE = re.compile(r"[,;|/]+")
TAG_PREFIX_RE = re.compile(r"^[a-z]{2}:", re.IGNORECASE)
URL_RE = re.compile(r"^https?://", re.IGNORECASE)

PRODUCT_NAME_FIELDS = (
    "product_name",
    "product_name_fr",
    "product_name_en",
    "generic_name",
    "generic_name_fr",
    "generic_name_en",
)
BRAND_FIELDS = ("brands", "brands_tags", "brand_owner")
CATEGORY_FIELDS = (
    "categories",
    "categories_tags",
    "categories_en",
    "main_category",
    "main_category_en",
)
COUNTRY_FIELDS = ("countries", "countries_tags", "countries_en")

# Conservative aliases useful for Moroccan grocery/beauty/household queries.
# The importer emits only known category aliases and repeated brands, avoiding
# noisy full product-title memorization.
CATEGORY_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("milk", "grocery", ("milk", "milks", "lait", "laits")),
    ("yogurt", "grocery", ("yogurt", "yoghurt", "yaourt", "raib")),
    ("cheese", "grocery", ("cheese", "fromage", "fromages")),
    ("butter", "grocery", ("butter", "beurre")),
    ("eggs", "grocery", ("eggs", "oeufs", "oeuf", "بيض")),
    ("bread", "grocery", ("bread", "pain", "khobz")),
    ("coffee", "grocery", ("coffee", "cafe", "café", "qahwa")),
    ("tea", "grocery", ("tea", "the", "thé", "atay")),
    ("water", "grocery", ("water", "eau", "mineral water")),
    ("juice", "grocery", ("juice", "jus")),
    ("oil", "grocery", ("oil", "huile", "zit", "zite")),
    ("pasta", "grocery", ("pasta", "pates", "pâtes", "spaghetti", "macaroni")),
    ("rice", "grocery", ("rice", "riz")),
    ("flour", "grocery", ("flour", "farine")),
    ("sugar", "grocery", ("sugar", "sucre")),
    ("chocolate", "grocery", ("chocolate", "chocolat")),
    ("cereal", "grocery", ("cereal", "cereals", "céréales", "corn flakes")),
    ("shampoo", "beauty", ("shampoo", "shampoos", "shampoing", "shampooing", "shampooings")),
    ("conditioner", "beauty", ("conditioner", "apres shampoing", "après shampoing")),
    ("soap", "beauty", ("soap", "soaps", "savon", "savons")),
    ("toothpaste", "beauty", ("toothpaste", "dentifrice")),
    ("deodorant", "beauty", ("deodorant", "déodorant", "deo", "déo")),
    ("perfume", "beauty", ("perfume", "parfum", "eau de parfum", "eau de toilette")),
    ("sunscreen", "beauty", ("sunscreen", "creme solaire", "crème solaire")),
    ("skin cream", "beauty", ("skin cream", "creme", "crème", "lait corps", "body lotion")),
    ("detergent", "household", ("detergent", "detergents", "lessive", "lessives", "laundry detergent")),
    ("dish soap", "household", ("dish soap", "liquide vaisselle", "vaisselle")),
    ("cleaner", "household", ("cleaner", "cleaners", "nettoyant", "nettoyants", "multi usage", "multi-usages")),
    ("tissues", "household", ("tissues", "mouchoirs")),
    ("toilet paper", "household", ("toilet paper", "papier toilette")),
)

FRENCH_ALIASES = {
    "lait", "laits", "yaourt", "fromage", "fromages", "beurre", "oeufs", "oeuf",
    "pain", "cafe", "café", "the", "thé", "eau", "jus", "huile", "pates", "pâtes",
    "riz", "farine", "sucre", "chocolat", "céréales", "shampoing", "shampooing",
    "apres shampoing", "après shampoing", "savon", "dentifrice", "déodorant", "déo",
    "parfum", "creme solaire", "crème solaire", "creme", "crème", "lait corps",
    "lessive", "liquide vaisselle", "vaisselle", "nettoyant", "mouchoirs", "papier toilette",
}

STOP_BRANDS = {
    "unknown", "sans marque", "no brand", "generic", "marque inconnue", "aucune", "n/a", "na"
}


@dataclass(frozen=True)
class Candidate:
    type: str
    canonical: str
    alias: str
    language: str
    category: str
    base_confidence: float
    notes: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.type, normalize_key(self.canonical), normalize_key(self.alias))


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


def clean_alias(value: str | None, *, max_words: int = 8, max_len: int = 80) -> str:
    if not value:
        return ""
    value = TAG_PREFIX_RE.sub("", value.strip())
    value = value.replace("_", " ").replace("-", " ")
    value = SPACE_RE.sub(" ", value).strip(" .,:;|/")
    if len(value) > max_len:
        return ""
    if len(value.split()) > max_words:
        return ""
    return value


def guess_language(alias: str) -> str:
    key = normalize_key(alias)
    if key in {normalize_key(item) for item in FRENCH_ALIASES}:
        return "fr"
    if re.search(r"[\u0600-\u06ff]", alias):
        return "ar"
    return "en"


def is_url(value: str | Path) -> bool:
    return bool(URL_RE.match(str(value)))


def input_name(value: str | Path) -> str:
    raw = str(value)
    if is_url(raw):
        parsed = urlparse(raw)
        return Path(parsed.path).name or parsed.netloc
    return Path(raw).name


def open_text(input_ref: str | Path) -> TextIO:
    raw = str(input_ref)
    if is_url(raw):
        request = Request(raw, headers={"User-Agent": "Smart-Shopper vocabulary importer/1.0"})
        response = urlopen(request, timeout=60)
        stream = response
        if raw.endswith(".gz"):
            stream = gzip.GzipFile(fileobj=response)
        return io.TextIOWrapper(stream, encoding="utf-8", errors="replace", newline="")

    path = Path(raw)
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="")
    return path.open("r", encoding="utf-8", errors="replace", newline="")


def detect_delimiter(handle: TextIO) -> str:
    sample = handle.read(8192)
    handle.seek(0)
    first_line = sample.splitlines()[0] if sample else ""
    return "\t" if "\t" in first_line else ","


def row_text(row: dict[str, str], fields: Iterable[str]) -> str:
    return " ".join((row.get(field) or "") for field in fields if row.get(field))


def split_multi_value(value: str | None) -> list[str]:
    if not value:
        return []
    parts = [clean_alias(part, max_words=5, max_len=60) for part in SPLIT_RE.split(value)]
    return [part for part in parts if part]


def country_allowed(row: dict[str, str], country_filters: set[str]) -> bool:
    if not country_filters:
        return True
    countries = normalize_key(row_text(row, COUNTRY_FIELDS))
    return any(country in countries for country in country_filters)


def detect_product_candidates(row: dict[str, str], *, source: str) -> list[Candidate]:
    haystack = normalize_key(row_text(row, (*PRODUCT_NAME_FIELDS, *CATEGORY_FIELDS)))
    candidates: list[Candidate] = []
    for canonical, category, aliases in CATEGORY_RULES:
        matched = False
        for alias in aliases:
            alias_key = normalize_key(alias)
            if not alias_key:
                continue
            pattern = rf"(?<!\w){re.escape(alias_key)}(?!\w)"
            if re.search(pattern, haystack):
                matched = True
                candidates.append(
                    Candidate(
                        type="product",
                        canonical=canonical,
                        alias=alias,
                        language=guess_language(alias),
                        category=category,
                        base_confidence=0.88,
                        notes=source,
                    )
                )
        if matched:
            candidates.append(
                Candidate(
                    type="product",
                    canonical=canonical,
                    alias=canonical,
                    language=guess_language(canonical),
                    category=category,
                    base_confidence=0.90,
                    notes=source,
                )
            )
    return candidates


def detect_brand_candidates(row: dict[str, str], *, source: str, category: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    for field in BRAND_FIELDS:
        for brand in split_multi_value(row.get(field)):
            key = normalize_key(brand)
            if len(key) < 2 or key in STOP_BRANDS:
                continue
            if brand.isdigit() or len(brand) > 60:
                continue
            candidates.append(
                Candidate(
                    type="brand",
                    canonical=brand.strip(),
                    alias=brand.strip(),
                    language="brand",
                    category=category or "general",
                    base_confidence=0.86,
                    notes=source,
                )
            )
    return candidates


def iter_open_facts_rows(input_ref: str | Path, *, max_rows: int | None = None) -> Iterable[dict[str, str]]:
    with open_text(input_ref) as handle:
        reader = csv.DictReader(handle, delimiter=detect_delimiter(handle))
        for index, row in enumerate(reader, start=1):
            if max_rows is not None and index > max_rows:
                break
            yield {str(key): (value or "") for key, value in row.items() if key is not None}


def convert_open_facts_exports(
    input_paths: Iterable[str | Path],
    *,
    source: str = "open_facts",
    country_filters: Iterable[str] = (),
    max_rows: int | None = None,
    min_count: int = 2,
    limit: int = 20000,
) -> list[dict[str, str]]:
    normalized_countries = {normalize_key(country) for country in country_filters if normalize_key(country)}
    counts: dict[tuple[str, str, str], int] = defaultdict(int)
    best: dict[tuple[str, str, str], Candidate] = {}

    for input_ref in input_paths:
        source_note = f"{source}:{input_name(input_ref)}"
        for row in iter_open_facts_rows(input_ref, max_rows=max_rows):
            if not country_allowed(row, normalized_countries):
                continue
            product_candidates = detect_product_candidates(row, source=source_note)
            detected_category = product_candidates[0].category if product_candidates else "general"
            candidates = [*product_candidates, *detect_brand_candidates(row, source=source_note, category=detected_category)]
            for candidate in candidates:
                if not clean_alias(candidate.alias):
                    continue
                key = candidate.key
                counts[key] += 1
                current = best.get(key)
                if current is None or candidate.base_confidence > current.base_confidence:
                    best[key] = candidate

    rows: list[dict[str, str]] = []
    for key, candidate in best.items():
        count = counts[key]
        if count < min_count:
            continue
        confidence = min(0.97, candidate.base_confidence + min(count, 25) * 0.002)
        rows.append(
            {
                "type": candidate.type,
                "canonical": candidate.canonical,
                "alias": candidate.alias,
                "language": candidate.language,
                "category": candidate.category,
                "confidence": f"{confidence:.2f}",
                "notes": f"{candidate.notes}; count={count}",
            }
        )

    rows.sort(key=lambda row: (row["type"], row["category"], row["canonical"].lower(), row["alias"].lower()))
    return rows[:limit]


def write_vocabulary(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=VOCAB_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Smart Shopper vocabulary from Open Facts exports.")
    parser.add_argument("--input", action="append", required=True, help="Open Facts CSV/TSV export path or URL; can be .gz. Repeatable.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Generated Smart Shopper vocabulary CSV path.")
    parser.add_argument("--source", default="open_facts", help="Notes prefix written to generated rows.")
    parser.add_argument("--country", action="append", default=[], help="Optional country filter, e.g. morocco, maroc, france. Repeatable.")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional per-input row limit for quick local or streaming runs.")
    parser.add_argument("--min-count", type=int, default=2, help="Minimum repeated observations before emitting an alias.")
    parser.add_argument("--limit", type=int, default=20000, help="Maximum generated rows.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_refs = [value for value in args.input]
    missing = [value for value in input_refs if not is_url(value) and not Path(value).exists()]
    if missing:
        raise SystemExit(f"Missing input file(s): {', '.join(missing)}")

    rows = convert_open_facts_exports(
        input_refs,
        source=args.source,
        country_filters=args.country,
        max_rows=args.max_rows,
        min_count=args.min_count,
        limit=args.limit,
    )
    output_path = Path(args.output)
    write_vocabulary(rows, output_path)
    print(f"Generated {len(rows)} vocabulary rows: {output_path.resolve()}")


if __name__ == "__main__":
    main()