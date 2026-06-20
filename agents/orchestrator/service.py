"""Kafka runtime for the Orchestrator Agent."""

from __future__ import annotations

import asyncio

from redis.asyncio import Redis
from typing import Any

from agents.orchestrator.agent import OrchestratorAgent
from agents.orchestrator.tools.cache_lookup import ProductCache
from agents.orchestrator.tools.ner_client import GrpcNerClient
from shared.config import Settings, get_settings
from shared.events.kafka import KafkaEventConsumer, KafkaEventProducer
from shared.events.schemas import InboundMessage, OutboundResponse
from shared.events.topics import (
    MSG_INBOUND,
    NER_EXTRACTED,
    RESPONSE_OUTBOUND,
    SCRAPE_TASK_ASSIGNED,
)


class OrchestratorService:
    def __init__(
        self,
        settings: Settings,
        agent: OrchestratorAgent | None = None,
        cache: ProductCache | None = None,
        consumer: Any | None = None,
        producer: Any | None = None,
    ) -> None:
        self._settings = settings
        self._agent = agent or OrchestratorAgent(
            GrpcNerClient(settings.ner_grpc_host, settings.ner_grpc_port)
        )
        self._consumer = consumer or KafkaEventConsumer(
            MSG_INBOUND,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.orchestrator_group_id,
            client_id=settings.kafka_client_id,
        )
        self._producer = producer or KafkaEventProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            client_id=settings.kafka_client_id,
        )
        if cache is None:
            redis = Redis.from_url(settings.redis_url, decode_responses=True)
            cache = ProductCache(redis)
        self._cache = cache

    async def start(self) -> None:
        await self._consumer.start()
        await self._producer.start()

    async def stop(self) -> None:
        await self._consumer.stop()
        await self._producer.stop()

    async def run_forever(self) -> None:
        await self.start()
        try:
            async for message in self._consumer.events(InboundMessage):
                await self.handle_message(message)
        finally:
            await self.stop()

    async def handle_message(self, message: InboundMessage) -> None:
        extracted, task = await self._agent.handle_inbound(message)
        cached_response = await self._cache.get(task.query)

        await self._producer.publish(NER_EXTRACTED, extracted, key=message.request_id)

        if cached_response:
            response = OutboundResponse(
                request_id=message.request_id,
                user_id=message.user_id,
                channel=message.channel,
                message=cached_response,
            )
            await self._producer.publish(RESPONSE_OUTBOUND, response, key=message.request_id)
            return

        await self._producer.publish(SCRAPE_TASK_ASSIGNED, task, key=message.request_id)


async def main() -> None:
    service = OrchestratorService(get_settings())
    await service.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
