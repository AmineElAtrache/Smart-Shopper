"""gRPC server for the rule-based NER placeholder."""

from __future__ import annotations

import asyncio

import grpc

from generated.ner.v1 import ner_pb2, ner_pb2_grpc
from models.ner.serve import extract_entities
from shared.config import get_settings


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
    server = grpc.aio.server()
    ner_pb2_grpc.add_NerServiceServicer_to_server(NerService(), server)
    server.add_insecure_port(f"{host}:{port}")
    await server.start()
    await server.wait_for_termination()


async def main() -> None:
    settings = get_settings()
    await serve(port=settings.ner_grpc_port)


if __name__ == "__main__":
    asyncio.run(main())
