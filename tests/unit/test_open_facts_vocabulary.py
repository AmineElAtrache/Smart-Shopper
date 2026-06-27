import csv
import gzip
import io

from models.ner import product_vocabulary as vocabulary
from scripts import import_open_facts_vocabulary as importer
from scripts.import_open_facts_vocabulary import convert_open_facts_exports, write_vocabulary
from shared.events.schemas import EntityType


def _clear_vocabulary_caches() -> None:
    vocabulary.load_vocabulary.cache_clear()
    vocabulary._exact_aliases.cache_clear()
    vocabulary._aliases_by_type.cache_clear()
    vocabulary._fuzzy_choices_by_type.cache_clear()
    vocabulary.city_aliases.cache_clear()


def test_open_facts_importer_generates_compact_vocabulary(tmp_path) -> None:
    source_path = tmp_path / "openfacts.tsv"
    source_path.write_text(
        "code\tproduct_name\tbrands\tcategories\tcountries\n"
        "1\tLait entier Centrale Danone\tCentrale Danone\tMilks,Dairy\tMorocco\n"
        "2\tShampooing doux\tLoreal\tShampoos,Beauty\tFrance\n"
        "3\tLaptop sleeve\tGeneric\tComputer accessories\tMorocco\n",
        encoding="utf-8",
    )

    rows = convert_open_facts_exports(
        [source_path],
        source="test_open_facts",
        country_filters=["morocco", "france"],
        min_count=1,
    )

    triples = {(row["type"], row["canonical"], row["alias"]) for row in rows}
    assert ("product", "milk", "lait") in triples
    assert ("product", "milk", "milks") in triples
    assert ("product", "shampoo", "shampoo") in triples
    assert ("brand", "Centrale Danone", "Centrale Danone") in triples
    assert ("brand", "Loreal", "Loreal") in triples
    assert all(row["canonical"] != "Laptop sleeve" for row in rows)


def test_open_facts_importer_streams_remote_gzip_url(monkeypatch) -> None:
    payload = (
        "code\tproduct_name\tbrands\tcategories\tcountries\n"
        "1\tSavon doux\tDove\tSoaps,Beauty\tMorocco\n"
    ).encode("utf-8")

    def fake_urlopen(request, timeout):
        assert timeout == 60
        assert "openfoodfacts" in request.full_url
        return io.BytesIO(gzip.compress(payload))

    monkeypatch.setattr(importer, "urlopen", fake_urlopen)

    rows = importer.convert_open_facts_exports(
        ["https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz"],
        country_filters=["morocco"],
        min_count=1,
    )

    triples = {(row["type"], row["canonical"], row["alias"]) for row in rows}
    assert ("product", "soap", "savon") in triples
    assert ("product", "soap", "soap") in triples
    assert ("brand", "Dove", "Dove") in triples


def test_external_vocabulary_file_is_loaded_by_ner_vocabulary(tmp_path, monkeypatch) -> None:
    base_path = tmp_path / "base.csv"
    external_path = tmp_path / "external.csv"
    write_vocabulary([], base_path)
    with external_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=["type", "canonical", "alias", "language", "category", "confidence", "notes"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "type": "product",
                "canonical": "soap",
                "alias": "savon",
                "language": "fr",
                "category": "beauty",
                "confidence": "0.90",
                "notes": "unit test",
            }
        )

    monkeypatch.setenv("SMART_SHOPPER_VOCAB_PATH", str(base_path))
    monkeypatch.setenv("SMART_SHOPPER_EXTERNAL_VOCAB_PATHS", str(external_path))
    _clear_vocabulary_caches()
    try:
        assert vocabulary.canonicalize_entity_value(EntityType.PRODUCT, "savon") == "soap"
        assert "soap" in vocabulary.normalize_text("bghit savon")
    finally:
        _clear_vocabulary_caches()