"""NER client abstraction used by the Orchestrator.

For the MVP this calls the local rule-based extractor. The class keeps the
same async shape we will later use for gRPC.
"""

from __future__ import annotations

from models.ner.serve import extract_entities
from shared.events.schemas import ExtractedEntity


class NerClient:
    async def extract(self, text: str, locale_hint: str | None = None) -> list[ExtractedEntity]:
        return extract_entities(text, locale_hint=locale_hint)
