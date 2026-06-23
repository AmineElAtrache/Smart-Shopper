"""gRPC server for the Smart Shopper NER model service."""

from __future__ import annotations

import asyncio

import grpc

from generated.ner.v1 import ner_pb2, ner_pb2_grpc
from models.ner.serve import extract_entities
from shared.config import get_settings
from shared.runtime import HealthServer


class NerService(ner_pb2_grpc.NerServiceServicer):
    async def Extract(
        self,
        request: ner_pb2.ExtractRequest,
        context: grpc.aio.ServicerContext,
    ) -> ner_pb2.ExtractResponse:
        entities = extract_entities(request.text, locale_hint=request.locale_hint or None)
        return ner_pb2.ExtractResponse(
            request_id=request.request_id if hasattr(request, "request_id") else "",
            entities=[
                ner_pb2.Entity(
                    type=entity.type,
                    value=entity.value,
                    confidence=entity.confidence,
                    attributes=entity.attributes,
                )
                for entity in entities
            ],
        )


async def serve(host: str = "0.0.0.0", port: int = 50051) -> None:
    settings = get_settings()
    health = HealthServer(host=settings.metrics_host, port=settings.metrics_port)
    await health.start()
    server = grpc.aio.server()
    ner_pb2_grpc.add_NerServiceServicer_to_server(NerService(), server)
    server.add_insecure_port(f"{host}:{port}")
    extract_entities(settings.ner_warmup_text)
    await server.start()
    try:
        await server.wait_for_termination()
    finally:
        await health.stop()


async def main() -> None:
    settings = get_settings()
    await serve(port=settings.ner_grpc_port)


if __name__ == "__main__":
    asyncio.run(main())
