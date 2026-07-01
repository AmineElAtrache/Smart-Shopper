"""NER client abstraction used by the Orchestrator."""

from __future__ import annotations

import asyncio

import grpc

from models.ner.serve import extract_entities
from shared.events.schemas import ExtractedEntity


class NerClient:
    async def extract(self, text: str, locale_hint: str | None = None) -> list[ExtractedEntity]:
        return extract_entities(text, locale_hint=locale_hint)


class GrpcNerClient:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 50051,
        timeout: float = 30.0,
        *,
        retries: int = 2,
    ) -> None:
        self._target = f"{host}:{port}"
        self._timeout = timeout
        self._retries = max(0, retries)

    async def extract(self, text: str, locale_hint: str | None = None) -> list[ExtractedEntity]:
        last_error: BaseException | None = None
        for attempt in range(self._retries + 1):
            try:
                return await self._extract_grpc(text, locale_hint)
            except grpc.aio.AioRpcError as exc:
                last_error = exc
                retryable = exc.code() in {
                    grpc.StatusCode.DEADLINE_EXCEEDED,
                    grpc.StatusCode.UNAVAILABLE,
                }
                if not retryable or attempt >= self._retries:
                    break
                wait_seconds = 2.0 * (attempt + 1)
                print(
                    f"[orchestrator] NER gRPC {exc.code().name}, "
                    f"retry {attempt + 1}/{self._retries} in {wait_seconds:.0f}s"
                )
                await asyncio.sleep(wait_seconds)

        print(
            f"[orchestrator] NER gRPC failed ({last_error}), "
            "using in-process fallback"
        )
        return extract_entities(text, locale_hint=locale_hint)

    async def _extract_grpc(self, text: str, locale_hint: str | None) -> list[ExtractedEntity]:
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
