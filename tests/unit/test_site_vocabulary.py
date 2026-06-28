"""Tests for vocabulary-backed site entity detection."""

from __future__ import annotations

from models.ner.product_vocabulary import detect_site_entities


def test_detect_site_entities_finds_jumia_and_avito() -> None:
    entities = detect_site_entities("bghit phone mn jumia w avito")

    values = {entity.value for entity in entities}
    assert "jumia" in values
    assert "avito" in values
    assert all(entity.type == "site" for entity in entities)
