"""Ambient Scheduler for background price-watch tasks."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import MongoClient

from shared.config import Settings, get_settings
from shared.events.kafka import KafkaEventConsumer, KafkaEventProducer
from shared.events.schemas import AmbientWatch, ScrapeTaskAssigned, WatchStatus, new_request_id
from shared.events.topics import AMBIENT_WATCH, SCRAPE_TASK_ASSIGNED
from shared.memory import UserMemory
from shared.memory.factory import create_user_memory
from shared.runtime import HealthServer


class AmbientScheduler:
    def __init__(
        self,
        settings: Settings,
        *,
        consumer: Any | None = None,
        producer: Any | None = None,
        user_memory: UserMemory | None = None,
    ) -> None:
        self._settings = settings
        self._consumer = consumer or KafkaEventConsumer(
            AMBIENT_WATCH,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.ambient_group_id,
            client_id=settings.kafka_client_id,
        )
        self._producer = producer or KafkaEventProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            client_id=settings.kafka_client_id,
        )
        client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=settings.mongo_connect_timeout_ms)
        self._collection = client[settings.mongo_db]["ambient_watches"]
        self._user_memory = user_memory
        self._running = False

    async def start(self) -> None:
        self._running = True
        await self._consumer.start()
        await self._producer.start()
        self._collection.create_index("watch_id", unique=True)
        self._collection.create_index("next_run_at")

    async def stop(self) -> None:
        self._running = False
        await self._consumer.stop()
        await self._producer.stop()

    async def handle_watch(self, watch: AmbientWatch) -> None:
        now = datetime.now(UTC)
        document = watch.model_dump()
        document.update(
            {
                "watch_id": watch.request_id,
                "status": WatchStatus.ACTIVE,
                "created_at": now,
                "updated_at": now,
                "next_run_at": now,
            }
        )
        self._collection.update_one(
            {"watch_id": watch.request_id},
            {"$set": document},
            upsert=True,
        )
        if self._user_memory is not None:
            await self._user_memory.save_watch(watch.user_id, document)

    async def run_due_once(self) -> int:
        now = datetime.now(UTC)
        due_watches = list(
            self._collection.find(
                {
                    "status": WatchStatus.ACTIVE,
                    "next_run_at": {"$lte": now},
                    "$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}],
                }
            )
        )
        for watch in due_watches:
            await self._emit_scrape_task(watch)
        return len(due_watches)

    async def run_forever(self) -> None:
        await self.start()
        scheduler_task = asyncio.create_task(self._schedule_loop())
        try:
            async for watch in self._consumer.events(AmbientWatch):
                await self.handle_watch(watch)
        finally:
            scheduler_task.cancel()
            await self.stop()

    async def _schedule_loop(self) -> None:
        while self._running:
            await self.run_due_once()
            await asyncio.sleep(30)

    async def _emit_scrape_task(self, watch: dict[str, Any]) -> None:
        interval_minutes = int(watch.get("interval_minutes") or 60)
        event_payload = {field: watch[field] for field in AmbientWatch.model_fields if field in watch}
        event = AmbientWatch.model_validate(event_payload)
        task = ScrapeTaskAssigned(
            request_id=new_request_id(),
            user_id=event.user_id,
            channel=event.channel,
            query=event.query,
        )
        await self._producer.publish(SCRAPE_TASK_ASSIGNED, task, key=task.request_id)
        self._collection.update_one(
            {"watch_id": watch["watch_id"]},
            {
                "$set": {
                    "updated_at": datetime.now(UTC),
                    "next_run_at": datetime.now(UTC) + timedelta(minutes=interval_minutes),
                }
            },
        )


async def main() -> None:
    settings = get_settings()
    health = HealthServer(host=settings.metrics_host, port=settings.metrics_port)
    await health.start()
    try:
        await AmbientScheduler(settings, user_memory=create_user_memory(settings)).run_forever()
    finally:
        await health.stop()


if __name__ == "__main__":
    asyncio.run(main())
