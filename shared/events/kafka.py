"""Small JSON helpers around aiokafka producers and consumers."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TypeVar

from pydantic import BaseModel

from shared.events.schemas import ErrorEvent
from shared.events.topics import ERROR_DEAD_LETTER
from shared.runtime.metrics import get_default_metrics
from shared.runtime.retry import retry_async

EventT = TypeVar("EventT", bound=BaseModel)


def encode_event(event: BaseModel) -> bytes:
    return event.model_dump_json().encode("utf-8")


def decode_event(payload: bytes, schema: type[EventT]) -> EventT:
    data = json.loads(payload.decode("utf-8"))
    return schema.model_validate(data)


class KafkaEventProducer:
    def __init__(
        self,
        bootstrap_servers: str,
        client_id: str = "smart-shopper",
        *,
        publish_attempts: int = 3,
    ) -> None:
        from aiokafka import AIOKafkaProducer

        self._publish_attempts = publish_attempts
        self._producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            client_id=client_id,
            value_serializer=encode_event,
            acks="all",
        )

    async def start(self) -> None:
        await self._producer.start()

    async def stop(self) -> None:
        await self._producer.stop()

    async def publish(self, topic: str, event: BaseModel, key: str | None = None) -> None:
        await retry_async(
            lambda: self._producer.send_and_wait(
                topic,
                event,
                key=key.encode("utf-8") if key else None,
            ),
            attempts=self._publish_attempts,
        )
        metric_topic = topic.replace(".", "_")
        get_default_metrics().increment(f"smart_shopper_{metric_topic}_total")

    async def publish_error(
        self,
        *,
        source_service: str,
        error: BaseException,
        topic: str | None = None,
        payload: dict | None = None,
        retryable: bool = False,
    ) -> None:
        event = ErrorEvent(
            source_service=source_service,
            topic=topic,
            error_type=type(error).__name__,
            message=str(error),
            payload=payload or {},
            retryable=retryable,
            timestamp=datetime.now(UTC),
        )
        get_default_metrics().increment("smart_shopper_errors_total")
        await self.publish(ERROR_DEAD_LETTER, event, key=event.request_id)


class KafkaEventConsumer:
    def __init__(
        self,
        *topics: str,
        bootstrap_servers: str,
        group_id: str,
        client_id: str = "smart-shopper",
        auto_offset_reset: str = "earliest",
    ) -> None:
        from aiokafka import AIOKafkaConsumer

        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            client_id=client_id,
            auto_offset_reset=auto_offset_reset,
        )

    async def start(self) -> None:
        await self._consumer.start()

    async def stop(self) -> None:
        await self._consumer.stop()

    async def events(self, schema: type[EventT]) -> AsyncIterator[EventT]:
        async for message in self._consumer:
            yield decode_event(message.value, schema)
