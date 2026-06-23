"""NER client abstraction used by the Orchestrator."""

from __future__ import annotations

import grpc

from models.ner.serve import extract_entities
from shared.events.schemas import ExtractedEntity


class NerClient:
    async def extract(self, text: str, locale_hint: str | None = None) -> list[ExtractedEntity]:
        return extract_entities(text, locale_hint=locale_hint)


class GrpcNerClient:
    def __init__(self, host: str = "localhost", port: int = 50051, timeout: float = 5.0) -> None:
        self._target = f"{host}:{port}"
        self._timeout = timeout

    async def extract(self, text: str, locale_hint: str | None = None) -> list[ExtractedEntity]:
        from generated.ner.v1 import ner_pb2, ner_pb2_grpc

        async with grpc.aio.insecure_channel(self._target) as channel:
            stub = ner_pb2_grpc.NerServiceStub(channel)
            response = await stub.Extract(
                ner_pb2.ExtractRequest(text=text, locale_hint=locale_hint or ""),
                timeout=self._timeout,
            )
        return [
            ExtractedEntity(
                type=entity.type,
                value=entity.value,
                confidence=entity.confidence,
                attributes=dict(entity.attributes),
            )
            for entity in response.entities
        ]
