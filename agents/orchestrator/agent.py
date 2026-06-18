"""Orchestrator Agent for inbound shopping requests."""

from __future__ import annotations

from agents.orchestrator.tools.ner_client import NerClient
from agents.orchestrator.tools.task_router import build_scrape_task
from shared.events.schemas import InboundMessage, NerExtracted, ScrapeTaskAssigned


class OrchestratorAgent:
    def __init__(self, ner_client: NerClient | None = None) -> None:
        self._ner_client = ner_client or NerClient()

    async def handle_inbound(self, message: InboundMessage) -> tuple[NerExtracted, ScrapeTaskAssigned]:
        entities = await self._ner_client.extract(message.text, locale_hint=message.locale_hint)
        extracted = NerExtracted(
            request_id=message.request_id,
            user_id=message.user_id,
            channel=message.channel,
            text=message.text,
            entities=entities,
        )
        task = build_scrape_task(message, entities)
        return extracted, task
