"""Agent Generator for final user-facing Smart Shopper responses."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Mapping

from agents.agent_generator.tools.behavior_analyzer import infer_language, resolve_generation_context
from agents.agent_generator.tools.darija_copy import (
    DARIJA_LABELS,
    build_darija_response,
    is_coherent_darija,
)
from agents.agent_generator.tools.llm_client import LlmClient
from agents.agent_generator.tools.response_validator import (
    ResponseValidationError,
    materialize_llm_response,
    validate_response,
)
from shared.config import Settings, get_settings
from shared.config.env import load_env_file
from shared.content_moderation import apply_outbound_moderation, blocked_outbound_message, moderate_outbound_text
from shared.events.kafka import KafkaEventConsumer, KafkaEventProducer
from shared.events.schemas import DecisionRanked, OutboundResponse, RankedProduct
from shared.events.topics import DECISION_RANKED, RESPONSE_OUTBOUND
from shared.memory import BehavioralMemory, GlobalMemory
from shared.memory.factory import create_behavioral_memory, create_global_memory
from shared.runtime import HealthServer
from shared.scrape_quality import is_mock_response_text

DEFAULT_KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
DEFAULT_PRODUCT_LABELS = {
    "price": "Price",
    "source": "Source",
    "score": "Score",
    "link": "Link",
}


def build_product_block(
    products: list[RankedProduct],
    *,
    labels: Mapping[str, str] | None = None,
    style: str = "labeled",
) -> str:
    label_map = {**DEFAULT_PRODUCT_LABELS, **dict(labels or {})}
    top_products = products[:3]
    lines: list[str] = []
    for index, product in enumerate(top_products, start=1):
        if style == "darija":
            lines.extend(
                [
                    f"{index}. {product.title}",
                    (
                        f"   {label_map['price']}: {product.price:g} {product.currency} "
                        f"| {product.source} | {label_map['score']} {product.score}/100"
                    ),
                    f"   {label_map['link']}: {product.url}",
                    "",
                ]
            )
            continue
        if style == "natural":
            lines.extend(
                [
                    (
                        f"{index}. {product.title} - {product.price:g} {product.currency} "
                        f"| {product.source} | {product.score}/100"
                    ),
                    f"   {product.url}",
                    "",
                ]
            )
            continue
        lines.extend(
            [
                f"{index}. {product.title}",
                f"   {label_map['price']}: {product.price:g} {product.currency}",
                f"   {label_map['source']}: {product.source}",
                f"   {label_map['score']}: {product.score}/100",
                f"   {label_map['link']}: {product.url}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def build_response_message(products: list[RankedProduct]) -> str:
    """Build a reliable response from ranked products without an LLM."""
    if not products:
        return (
            "Hi, I could not find product options yet. "
            "Send me what you are looking for and your budget, and I will search for options."
        )

    top_products = products[:3]
    intro = f"Here are {len(top_products)} option{'s' if len(top_products) != 1 else ''} from your search."
    from agents.agent_generator.tools.response_copy import localized_closing

    closing = localized_closing("en", seed=intro)
    return build_composed_message(
        products,
        intro=intro,
        product_header="Details:",
        best_reason=closing,
        why_this_order=None,
        next_step=None,
    )


def build_composed_message(
    products: list[RankedProduct],
    *,
    intro: str,
    best_reason: str,
    product_header: str | None = None,
    why_this_order: str | None = None,
    next_step: str | None = None,
    labels: Mapping[str, str] | None = None,
    product_style: str = "labeled",
) -> str:
    product_block = build_product_block(products, labels=labels, style=product_style)
    parts = [intro.strip()]
    if product_header:
        parts.append(product_header.strip())
    parts.append(product_block)
    parts.append(best_reason.strip())
    if why_this_order:
        parts.append(why_this_order.strip())
    if next_step:
        parts.append(next_step.strip())
    return "\n\n".join(part for part in parts if part)


def build_localized_response(event: DecisionRanked) -> str:
    language = infer_language(event.user_text or "")
    if language == "darija":
        return build_darija_response(event)
    from agents.agent_generator.tools.response_copy import build_standard_response

    return build_standard_response(event, language)


def build_outbound_response(event: DecisionRanked) -> OutboundResponse:
    return OutboundResponse(
        request_id=event.request_id,
        user_id=event.user_id,
        channel=event.channel,
        message=build_localized_response(event),
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
        settings: Settings | None = None,
        producer: KafkaEventProducer | None = None,
        global_memory: GlobalMemory | None = None,
        behavioral_memory: BehavioralMemory | None = None,
        llm_client: LlmClient | None = None,
    ) -> None:
        self._config = config
        self._settings = settings
        self._producer = producer or KafkaEventProducer(
            config.kafka_bootstrap_servers,
            client_id="agent-generator",
        )
        self._global_memory = global_memory
        self._behavioral_memory = behavioral_memory
        self._llm_client = llm_client
        if settings is not None:
            self._llm_client = self._llm_client or LlmClient(settings)
            self._global_memory = self._global_memory or create_global_memory(settings)
            self._behavioral_memory = self._behavioral_memory or create_behavioral_memory(settings)

    async def handle_ranked(self, event: DecisionRanked) -> OutboundResponse | None:
        if event.watch_id:
            print(
                f"[generator] skipping ambient watch result request_id={event.request_id} "
                f"watch_id={event.watch_id}"
            )
            return None

        response = build_outbound_response(event)
        behavior_context = None
        if self._behavioral_memory is not None:
            behavior_context = await self._behavioral_memory.build_generation_context(event.user_id)
        behavior_context = resolve_generation_context(event, behavior_context)
        if self._llm_client is not None and event.products:
            llm_text = await self._llm_client.generate_recommendation(
                event,
                response.message,
                behavior_context=behavior_context,
            )
            try:
                message = materialize_llm_response(event, llm_text, fallback_message=response.message)
                validate_response(event, message)
            except ResponseValidationError as exc:
                print(f"[generator] generated response failed validation, using template: {exc}")
                message = build_localized_response(event)
            response = OutboundResponse(
                request_id=event.request_id,
                user_id=event.user_id,
                channel=event.channel,
                message=message,
            )
        elif event.products:
            print(f"[generator] template-only response request_id={event.request_id}")
        else:
            print(
                f"[generator] no products; skipping LLM request_id={event.request_id}"
            )

        response = self._apply_content_moderation(event, response)
        await self._producer.publish(RESPONSE_OUTBOUND, response, key=event.request_id)
        if (
            self._global_memory is not None
            and event.query is not None
            and event.products
            and not is_mock_response_text(response.message)
            and moderate_outbound_text(
                response.message,
                enabled=self._content_moderation_enabled(),
            ).allowed
        ):
            await self._global_memory.set_cached_response(event.query, response.message)
        if self._behavioral_memory is not None:
            await self._behavioral_memory.record_generation(event, response)
        return response

    def _content_moderation_enabled(self) -> bool:
        if self._settings is None:
            return True
        return self._settings.governance_content_moderation_enabled

    def _apply_content_moderation(
        self,
        event: DecisionRanked,
        response: OutboundResponse,
    ) -> OutboundResponse:
        reference_text = event.user_text or ""
        fallback = (
            build_localized_response(event)
            if event.products
            else blocked_outbound_message(reference_text=reference_text)
        )
        message, result = apply_outbound_moderation(
            response.message,
            fallback=fallback,
            enabled=self._content_moderation_enabled(),
            reference_text=reference_text,
        )
        if not result.allowed:
            print(
                f"[generator] content moderation blocked request_id={event.request_id}: "
                f"{result.summary}"
            )
        if message == response.message:
            return response
        return OutboundResponse(
            request_id=response.request_id,
            user_id=response.user_id,
            channel=response.channel,
            message=message,
        )

    async def run(self) -> None:
        consumer = KafkaEventConsumer(
            DECISION_RANKED,
            bootstrap_servers=self._config.kafka_bootstrap_servers,
            group_id=self._settings.generator_group_id if self._settings else "agent-generator",
            client_id="agent-generator",
        )

        await self._producer.start()
        await consumer.start()
        print("Agent generator started. Waiting for decision.ranked events.")
        try:
            async for event in consumer.events(DecisionRanked):
                response = await self.handle_ranked(event)
                if response is not None:
                    print(f"Published response.outbound for {response.request_id}.")
        finally:
            await consumer.stop()
            await self._producer.stop()


async def main() -> None:
    settings = get_settings()
    health = HealthServer(host=settings.metrics_host, port=settings.metrics_port)
    await health.start()
    try:
        await AgentGenerator(
            config=AgentGeneratorConfig(kafka_bootstrap_servers=settings.kafka_bootstrap_servers),
            settings=settings,
        ).run()
    finally:
        await health.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Agent generator stopped.")
