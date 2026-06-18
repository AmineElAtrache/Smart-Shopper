"""Small JSON helpers around aiokafka producers and consumers."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TypeVar

from pydantic import BaseModel

EventT = TypeVar("EventT", bound=BaseModel)


def encode_event(event: BaseModel) -> bytes:
    return event.model_dump_json().encode("utf-8")


def decode_event(payload: bytes, schema: type[EventT]) -> EventT:
    data = json.loads(payload.decode("utf-8"))
    return schema.model_validate(data)


class KafkaEventProducer:
    def __init__(self, bootstrap_servers: str, client_id: str = "smart-shopper") -> None:
        from aiokafka import AIOKafkaProducer

        self._producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            client_id=client_id,
            value_serializer=encode_event,
        )

    async def start(self) -> None:
        await self._producer.start()

    async def stop(self) -> None:
        await self._producer.stop()

    async def publish(self, topic: str, event: BaseModel, key: str | None = None) -> None:
        await self._producer.send_and_wait(
            topic,
            event,
            key=key.encode("utf-8") if key else None,
        )


class KafkaEventConsumer:
    def __init__(
        self,
        *topics: str,
        bootstrap_servers: str,
        group_id: str,
        client_id: str = "smart-shopper",
    ) -> None:
        from aiokafka import AIOKafkaConsumer

        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            client_id=client_id,
        )

    async def start(self) -> None:
        await self._consumer.start()

    async def stop(self) -> None:
        await self._consumer.stop()

    async def events(self, schema: type[EventT]) -> AsyncIterator[EventT]:
        async for message in self._consumer:
            yield decode_event(message.value, schema)
