"""Kafka runtime for the Decision Agent."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from agents.decision.agent import DecisionAgent
from shared.config import Settings, get_settings
from shared.events.kafka import KafkaEventConsumer, KafkaEventProducer
from shared.events.schemas import ProductQuery, RawProduct
from shared.events.topics import DECISION_RANKED, PRICE_HISTORY, SCRAPE_RAW
from shared.memory.factory import create_global_memory
from shared.memory.global_memory import GlobalMemory
from shared.memory.tier1_hooks import record_ranked_prices
from shared.runtime import HealthServer


class DecisionService:
    def __init__(
        self,
        settings: Settings,
        agent: DecisionAgent | None = None,
        consumer: Any | None = None,
        producer: Any | None = None,
        global_memory: GlobalMemory | None = None,
    ) -> None:
        self._settings = settings
        self._agent = agent or DecisionAgent()
        self._global_memory = global_memory
        self._consumer = consumer or KafkaEventConsumer(
            SCRAPE_RAW,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.decision_group_id,
            client_id=settings.kafka_client_id,
        )
        self._producer = producer or KafkaEventProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            client_id=settings.kafka_client_id,
        )
        self._pending: dict[str, list[RawProduct]] = defaultdict(list)
        self._flush_tasks: dict[str, asyncio.Task[None]] = {}

    async def start(self) -> None:
        await self._consumer.start()
        await self._producer.start()

    async def stop(self) -> None:
        for task in self._flush_tasks.values():
            task.cancel()
        await self._consumer.stop()
        await self._producer.stop()

    async def run_forever(self) -> None:
        await self.start()
        try:
            async for product in self._consumer.events(RawProduct):
                await self.handle_product(product)
        finally:
            await self.stop()

    async def handle_product(self, product: RawProduct) -> None:
        print(f"[decision] received scrape.raw request_id={product.request_id} source={product.source}")
        self._pending[product.request_id].append(product)
        if product.request_id not in self._flush_tasks:
            self._flush_tasks[product.request_id] = asyncio.create_task(
                self._flush_after_wait(product.request_id)
            )

    async def _flush_after_wait(self, request_id: str) -> None:
        await asyncio.sleep(self._settings.decision_batch_wait_seconds)
        await self.flush_request(request_id)

    async def flush_request(self, request_id: str) -> None:
        products = self._pending.pop(request_id, [])
        self._flush_tasks.pop(request_id, None)
        if not products:
            return

        first = products[0]
        user_text = str(first.metadata.get("user_text") or "").strip() or None
        ranked = self._agent.rank(
            request_id=request_id,
            user_id=first.user_id or "unknown",
            channel=first.channel,
            query=first.query or ProductQuery(),
            products=products,
            watch_id=str(first.metadata.get("watch_id") or "") or None,
            user_text=user_text,
        )
        await self._producer.publish(DECISION_RANKED, ranked, key=request_id)
        if self._global_memory is not None:
            snapshots = await record_ranked_prices(self._global_memory, ranked)
            for snapshot in snapshots:
                await self._producer.publish(PRICE_HISTORY, snapshot, key=request_id)
        print(f"[decision] published decision.ranked request_id={request_id} products={len(products)}")


async def main() -> None:
    settings = get_settings()
    health = HealthServer(host=settings.metrics_host, port=settings.metrics_port)
    await health.start()
    try:
        service = DecisionService(settings, global_memory=create_global_memory(settings))
        await service.run_forever()
    finally:
        await health.stop()


if __name__ == "__main__":
    asyncio.run(main())
