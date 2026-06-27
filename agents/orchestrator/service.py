"""Kafka runtime for the Orchestrator Agent."""

from __future__ import annotations

import asyncio
from typing import Any

from redis.asyncio import Redis

from agents.orchestrator.agent import OrchestratorAgent
from agents.orchestrator.tools.conversational_llm import ConversationalLlmClient
from agents.orchestrator.tools.intent_gate import should_run_product_search
from agents.orchestrator.tools.cache_lookup import ProductCache
from shared.scrape_quality import is_mock_response_text
from agents.orchestrator.tools.ner_client import GrpcNerClient
from shared.config import Settings, get_settings
from shared.content_moderation import blocked_outbound_message, moderate_outbound_text
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
        conversational_llm: ConversationalLlmClient | None = None,
    ) -> None:
        self._settings = settings
        self._agent = agent or OrchestratorAgent(
            GrpcNerClient(
                settings.ner_grpc_host,
                settings.ner_grpc_port,
                timeout=settings.ner_grpc_timeout_seconds,
            ),
            settings=settings,
        )
        self._conversational_llm = conversational_llm or ConversationalLlmClient(settings)
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
        try:
            await self._handle_message(message)
        except Exception as exc:
            print(f"[orchestrator] failed request_id={message.request_id}: {exc}")
            response = OutboundResponse(
                request_id=message.request_id,
                user_id=message.user_id,
                channel=message.channel,
                message=(
                    "Sorry, something went wrong while processing your request. "
                    "Please try again in a moment."
                ),
            )
            await self._producer.publish(RESPONSE_OUTBOUND, response, key=message.request_id)

    async def _handle_message(self, message: InboundMessage) -> None:
        extracted, task = await self._agent.handle_inbound(message)

        await self._producer.publish(NER_EXTRACTED, extracted, key=message.request_id)
        print(f"[orchestrator] published ner.extracted request_id={message.request_id}")

        if not should_run_product_search(message.text, task.query):
            reply = await self._conversational_llm.generate_reply(message)
            reply = self._moderate_outbound_message(reply, reference_text=message.text)
            response = OutboundResponse(
                request_id=message.request_id,
                user_id=message.user_id,
                channel=message.channel,
                message=reply,
            )
            await self._producer.publish(RESPONSE_OUTBOUND, response, key=message.request_id)
            print(
                f"[orchestrator] conversational reply; skipped scrape "
                f"request_id={message.request_id}"
            )
            return

        if self._user_memory is not None:
            task.query = await self._user_memory.apply_preferences(message.user_id, task.query)
            await self._user_memory.record_search(message, task.query)
        cached_response = await self._cache.get(task.query)

        if cached_response and not is_mock_response_text(cached_response):
            if self._is_outbound_message_allowed(cached_response):
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
            print(
                f"[orchestrator] cached response blocked by content moderation; "
                f"re-scraping request_id={message.request_id}"
            )
        if cached_response and is_mock_response_text(cached_response):
            print(
                f"[orchestrator] ignored cached mock response; "
                f"re-scraping request_id={message.request_id}"
            )

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

    def _content_moderation_enabled(self) -> bool:
        return self._settings.governance_content_moderation_enabled

    def _is_outbound_message_allowed(self, message: str) -> bool:
        return moderate_outbound_text(
            message,
            enabled=self._content_moderation_enabled(),
        ).allowed

    def _moderate_outbound_message(self, message: str, *, reference_text: str) -> str:
        if self._is_outbound_message_allowed(message):
            return message
        safe_message = blocked_outbound_message(reference_text=reference_text)
        print(f"[orchestrator] content moderation replaced outbound reply for safety")
        return safe_message


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
