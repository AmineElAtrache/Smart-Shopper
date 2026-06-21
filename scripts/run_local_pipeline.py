"""Run the MVP pipeline locally without Telegram or Kafka.

This script is an integration smoke test for developers. It sends one fake
inbound shopping request through the same components used by the live services:
Orchestrator -> Mock Scraper -> Decision Agent -> Agent Generator.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from agents.agent_generator.agent import build_outbound_response
from agents.decision.agent import DecisionAgent
from agents.orchestrator.agent import OrchestratorAgent
from agents.webscraping.agent import build_mock_products
from shared.events.schemas import Channel, InboundMessage, OutboundResponse


@dataclass(frozen=True)
class IntegrationResult:
    inbound: InboundMessage
    outbound: OutboundResponse
    products_count: int
    top_score: int


async def run_pipeline(text: str, *, user_id: str = "telegram_123") -> IntegrationResult:
    inbound = InboundMessage(user_id=user_id, channel=Channel.TELEGRAM, text=text)

    orchestrator = OrchestratorAgent()
    extracted, task = await orchestrator.handle_inbound(inbound)
    print(f"[integration] extracted {len(extracted.entities)} entities for {inbound.request_id}")

    raw_products = build_mock_products(task)
    print(f"[integration] mock scraper produced {len(raw_products)} products")

    ranked = DecisionAgent().rank(
        request_id=inbound.request_id,
        user_id=inbound.user_id,
        channel=inbound.channel,
        query=task.query,
        products=raw_products,
    )
    print(f"[integration] decision ranked {len(ranked.products)} products")

    outbound = build_outbound_response(ranked)
    return IntegrationResult(
        inbound=inbound,
        outbound=outbound,
        products_count=len(raw_products),
        top_score=ranked.products[0].score if ranked.products else 0,
    )


async def main() -> None:
    result = await run_pipeline("Bghit Samsung phone b 3000 dh")
    print("\n=== Final response ===")
    print(result.outbound.message)
    print("\n=== Summary ===")
    print(f"request_id={result.inbound.request_id}")
    print(f"products_count={result.products_count}")
    print(f"top_score={result.top_score}")


if __name__ == "__main__":
    asyncio.run(main())
