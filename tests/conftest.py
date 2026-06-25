"""Shared pytest fixtures for Smart Shopper unit tests."""

from __future__ import annotations

import pytest

from models.ner import serve as ner_serve


class FakeNerPipeline:
    def __call__(self, text: str) -> list[dict[str, object]]:
        normalized = text.lower()
        predictions: list[dict[str, object]] = []

        if "samsung" in normalized:
            predictions.append({"entity_group": "BRAND", "word": "Samsung", "score": 0.99})
        if "iphone" in normalized:
            predictions.append({"entity_group": "BRAND", "word": "iPhone", "score": 0.99})
        if "phone" in normalized:
            predictions.append({"entity_group": "PRODUCT", "word": "phone", "score": 0.98})
        if "pc" in normalized:
            predictions.append({"entity_group": "PRODUCT", "word": "pc", "score": 0.99})
        if "fridge" in normalized:
            predictions.append({"entity_group": "PRODUCT", "word": "fridge", "score": 0.99})
        if "ykone" in normalized:
            predictions.append({"entity_group": "BRAND", "word": "Kone", "score": 0.58})
        if "hp" in normalized:
            predictions.append({"entity_group": "BRAND", "word": "hp", "score": 0.99})
        if "fes" in normalized:
            predictions.append({"entity_group": "CITY", "word": "fes", "score": 0.99})
        if "casablanca" in normalized:
            predictions.append({"entity_group": "CITY", "word": "Casablanca", "score": 0.99})
        if "black" in normalized:
            predictions.append({"entity_group": "COLOR", "word": "black", "score": 0.99})
        if "3000" in normalized:
            predictions.append({"entity_group": "PRICE", "word": "3000 dh", "score": 0.99})
        if "6000" in normalized:
            predictions.append({"entity_group": "PRICE", "word": "6000dh", "score": 0.99})

        return predictions


@pytest.fixture(autouse=True)
def fake_hf_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid loading the real Hugging Face model during unit tests."""
    monkeypatch.setenv("SMART_SHOPPER_NER_BACKEND", "auto")
    monkeypatch.setattr(ner_serve, "_get_pipeline", lambda model_id: FakeNerPipeline())
