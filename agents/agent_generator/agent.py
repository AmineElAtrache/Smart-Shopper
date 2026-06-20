"""Template-based Agent Generator for the Smart Shopper MVP."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from shared.config.env import load_env_file
from shared.events.kafka import KafkaEventConsumer, KafkaEventProducer
from shared.events.schemas import DecisionRanked, OutboundResponse, RankedProduct
from shared.events.topics import DECISION_RANKED, RESPONSE_OUTBOUND

DEFAULT_KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"


def build_response_message(products: list[RankedProduct]) -> str:
    """Build a readable MVP response from ranked products."""
    if not products:
        return (
            "I could not find good product options for this request yet. "
            "Try a different budget, brand, or product name."
        )

    top_products = products[:3]
    lines = [f"I found {len(top_products)} good option{'s' if len(top_products) != 1 else ''} for you:"]
    for index, product in enumerate(top_products, start=1):
        lines.extend(
            [
                "",
                f"{index}. {product.title}",
                f"   Price: {product.price:g} {product.currency}",
                f"   Source: {product.source}",
                f"   Score: {product.score}/100",
                f"   Link: {product.url}",
            ]
        )

    best = top_products[0]
    lines.extend(
        [
            "",
            (
                f"Best choice: {best.title} because it has the strongest overall score, "
                f"a good price, and availability marked as {best.availability}."
            ),
        ]
    )
    return "\n".join(lines)


def build_outbound_response(event: DecisionRanked) -> OutboundResponse:
    return OutboundResponse(
        request_id=event.request_id,
        user_id=event.user_id,
        channel=event.channel,
        message=build_response_message(event.products),
    )


@dataclass(frozen=True)
class AgentGeneratorConfig:
    kafka_bootstrap_servers: str = DEFAULT_KAFKA_BOOTSTRAP_SERVERS

    @classmethod
    def from_env(cls) -> "AgentGeneratorConfig":
        load_env_file()
        return cls(
            kafka_bootstrap_servers=os.getenv(
                "KAFKA_BOOTSTRAP_SERVERS", DEFAULT_KAFKA_BOOTSTRAP_SERVERS
            )
        )


class AgentGenerator:
    def __init__(
        self,
        *,
        config: AgentGeneratorConfig,
        producer: KafkaEventProducer | None = None,
    ) -> None:
        self._config = config
        self._producer = producer or KafkaEventProducer(
            config.kafka_bootstrap_servers,
            client_id="agent-generator",
        )

    async def handle_ranked(self, event: DecisionRanked) -> OutboundResponse:
        response = build_outbound_response(event)
        await self._producer.publish(RESPONSE_OUTBOUND, response, key=event.request_id)
        return response

    async def run(self) -> None:
        consumer = KafkaEventConsumer(
            DECISION_RANKED,
            bootstrap_servers=self._config.kafka_bootstrap_servers,
            group_id="agent-generator",
            client_id="agent-generator",
        )

        await self._producer.start()
        await consumer.start()
        print("Agent generator started. Waiting for decision.ranked events.")
        try:
            async for event in consumer.events(DecisionRanked):
                response = await self.handle_ranked(event)
                print(f"Published response.outbound for {response.request_id}.")
        finally:
            await consumer.stop()
            await self._producer.stop()


async def main() -> None:
    await AgentGenerator(config=AgentGeneratorConfig.from_env()).run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Agent generator stopped.")
