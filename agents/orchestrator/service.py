"""Kafka runtime for the Orchestrator Agent."""

from __future__ import annotations

import asyncio
from typing import Any

from redis.asyncio import Redis

from agents.orchestrator.agent import OrchestratorAgent
from agents.orchestrator.tools.cache_lookup import ProductCache
from agents.orchestrator.tools.ner_client import GrpcNerClient
from shared.config import Settings, get_settings
from shared.events.kafka import KafkaEventConsumer, KafkaEventProducer
from shared.events.schemas import AmbientWatch, EntityType, InboundMessage, OutboundResponse
from shared.events.topics import (
    AMBIENT_WATCH,
    MSG_INBOUND,
    NER_EXTRACTED,
    RESPONSE_OUTBOUND,
    SCRAPE_TASK_ASSIGNED,
)
from shared.memory import UserMemory
from shared.memory.factory import create_user_memory
from shared.runtime import HealthServer


class OrchestratorService:
    def __init__(
        self,
        settings: Settings,
        agent: OrchestratorAgent | None = None,
        cache: ProductCache | None = None,
        user_memory: UserMemory | None = None,
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
        self._user_memory = user_memory

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
        print(f"[orchestrator] received msg.inbound request_id={message.request_id}")
        extracted, task = await self._agent.handle_inbound(message)
        if self._user_memory is not None:
            task.query = await self._user_memory.apply_preferences(message.user_id, task.query)
            await self._user_memory.record_search(message, task.query)
        cached_response = await self._cache.get(task.query)

        await self._producer.publish(NER_EXTRACTED, extracted, key=message.request_id)
        print(f"[orchestrator] published ner.extracted request_id={message.request_id}")

        if cached_response:
            response = OutboundResponse(
                request_id=message.request_id,
                user_id=message.user_id,
                channel=message.channel,
                message=cached_response,
            )
            await self._producer.publish(RESPONSE_OUTBOUND, response, key=message.request_id)
            print(f"[orchestrator] cache hit; published response.outbound request_id={message.request_id}")
            if _has_watch_intent(extracted.entities):
                await self._publish_watch(message, task)
            return

        await self._producer.publish(SCRAPE_TASK_ASSIGNED, task, key=message.request_id)
        print(f"[orchestrator] published scrape.task.assigned request_id={message.request_id}")
        if _has_watch_intent(extracted.entities):
            await self._publish_watch(message, task)

    async def _publish_watch(self, message: InboundMessage, task) -> None:
        watch = AmbientWatch(
            request_id=message.request_id,
            user_id=message.user_id,
            channel=message.channel,
            query=task.query,
        )
        await self._producer.publish(AMBIENT_WATCH, watch, key=message.request_id)
        print(f"[orchestrator] published ambient.watch request_id={message.request_id}")


def _has_watch_intent(entities) -> bool:
    return any(entity.type == EntityType.INTENT and entity.value == "watch" for entity in entities)


async def main() -> None:
    settings = get_settings()
    health = HealthServer(host=settings.metrics_host, port=settings.metrics_port)
    await health.start()
    try:
        service = OrchestratorService(settings, user_memory=create_user_memory(settings))
        await service.run_forever()
    finally:
        await health.stop()


if __name__ == "__main__":
    asyncio.run(main())
