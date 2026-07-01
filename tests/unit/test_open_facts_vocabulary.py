import csv
import gzip
import io

from models.ner import product_vocabulary as vocabulary
from scripts import import_open_facts_vocabulary as importer
from scripts.import_open_facts_vocabulary import (
    configure_csv_field_limit,
    convert_open_facts_exports,
    write_vocabulary,
)
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

    class NonSeekableResponse(io.RawIOBase):
        def __init__(self, data: bytes) -> None:
            self._buffer = io.BytesIO(data)

        def read(self, size: int = -1) -> bytes:
            return self._buffer.read(size)

        def readable(self) -> bool:
            return True

        def seekable(self) -> bool:
            return False

    def fake_urlopen(request, timeout):
        assert timeout == 60
        assert "openfoodfacts" in request.full_url
        return NonSeekableResponse(gzip.compress(payload))

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


def test_iter_csv_lines_works_without_seek() -> None:
    payload = "code\tproduct_name\tcountries\n2\tLait\tMorocco\n"
    handle = io.StringIO(payload)
    delimiter, lines = importer._iter_csv_lines(handle)
    rows = list(csv.DictReader(lines, delimiter=delimiter))

    assert delimiter == "\t"
    assert rows[0]["product_name"] == "Lait"


def test_iter_csv_lines_parses_oversized_fields() -> None:
    configure_csv_field_limit()
    huge_value = "x" * 200_000
    payload = f"code\tproduct_name\tcountries\n3\t{huge_value}\tMorocco\n"
    handle = io.StringIO(payload)
    delimiter, lines = importer._iter_csv_lines(handle)
    rows = list(csv.DictReader(lines, delimiter=delimiter))

    assert delimiter == "\t"
    assert rows[0]["product_name"] == huge_value


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