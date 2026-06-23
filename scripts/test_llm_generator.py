"""Test Agent Generator with a real LLM provider without running NER, Kafka, or scrapers.

Use this for Groq/OpenAI/Gemini smoke tests. It builds a deterministic
DecisionRanked event and sends it through the real AgentGenerator class.
"""

from __future__ import annotations

import asyncio

from agents.agent_generator.agent import AgentGenerator, AgentGeneratorConfig, build_outbound_response
from shared.config import get_settings
from shared.events.schemas import (
    Availability,
    Channel,
    DecisionRanked,
    ProductQuery,
    RankedProduct,
    ScoreBreakdown,
)
from shared.events.topics import RESPONSE_OUTBOUND


class PrintOnlyProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


class NoopGlobalMemory:
    async def set_cached_response(self, query, message) -> None:
        return None


class NoopBehavioralMemory:
    async def build_generation_context(self, user_id):
        return {"tone": "concise", "language": "en"}

    async def record_generation(self, event, response) -> None:
        return None


def build_sample_ranked() -> DecisionRanked:
    return DecisionRanked(
        request_id="req_llm_test",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="phone", brand="Samsung", budget=3000),
        products=[
            RankedProduct(
                title="Samsung Galaxy A15 128GB",
                price=2499,
                source="jumia",
                url="https://example.com/jumia-a15",
                availability=Availability.IN_STOCK,
                score=88,
                score_breakdown=ScoreBreakdown(price=36, trust=27, quality=17, availability=8),
            ),
            RankedProduct(
                title="Samsung Galaxy A05",
                price=1890,
                source="jumia",
                url="https://example.com/jumia-a05",
                availability=Availability.IN_STOCK,
                score=84,
                score_breakdown=ScoreBreakdown(price=38, trust=24, quality=14, availability=8),
            ),
            RankedProduct(
                title="Samsung Galaxy A15 phone",
                price=3300,
                source="avito",
                url="https://example.com/avito-a15",
                availability=Availability.UNKNOWN,
                score=64,
                score_breakdown=ScoreBreakdown(price=25, trust=18, quality=15, availability=6),
            ),
        ],
    )


async def main() -> None:
    settings = get_settings()
    event = build_sample_ranked()
    template = build_outbound_response(event).message
    producer = PrintOnlyProducer()
    generator = AgentGenerator(
        config=AgentGeneratorConfig(kafka_bootstrap_servers=settings.kafka_bootstrap_servers),
        settings=settings,
        producer=producer,
        global_memory=NoopGlobalMemory(),
        behavioral_memory=NoopBehavioralMemory(),
    )

    response = await generator.handle_ranked(event)
    if response is None:
        raise RuntimeError("Agent Generator did not produce a response.")

    print("=== LLM Generator Test ===")
    print(f"provider={settings.llm_provider}")
    print(f"model={settings.llm_model}")
    print(f"published_topic={producer.published[0][0] if producer.published else None}")
    print(f"used_llm={response.message != template}")
    print("\n=== Final response ===")
    print(response.message)

    if producer.published and producer.published[0][0] != RESPONSE_OUTBOUND:
        raise RuntimeError(f"Unexpected topic: {producer.published[0][0]}")


if __name__ == "__main__":
    asyncio.run(main())
