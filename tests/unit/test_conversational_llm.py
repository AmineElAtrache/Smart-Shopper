import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agents.orchestrator.service import OrchestratorService
from agents.orchestrator.tools.conversational_llm import (
    ConversationalLlmClient,
    clean_conversational_output,
)
from agents.orchestrator.tools.conversational_reply import build_conversational_reply
from shared.config import Settings
from shared.events.schemas import InboundMessage
from shared.events.topics import NER_EXTRACTED, RESPONSE_OUTBOUND, SCRAPE_TASK_ASSIGNED


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


class EmptyCache:
    async def get(self, query):
        return None


class FakeConsumer:
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


class FakeAgent:
    async def handle_inbound(self, message):
        from shared.events.schemas import NerExtracted, ProductQuery, ScrapeTaskAssigned

        extracted = NerExtracted(
            request_id=message.request_id,
            user_id=message.user_id,
            channel=message.channel,
            text=message.text,
            entities=[],
        )
        task = ScrapeTaskAssigned(
            request_id=message.request_id,
            user_id=message.user_id,
            channel=message.channel,
            query=ProductQuery(),
        )
        return extracted, task


def test_clean_conversational_output_strips_general_reply_prefix() -> None:
    assert clean_conversational_output("GENERAL_REPLY: Hello there!") == "Hello there!"


def test_conversational_llm_uses_template_when_provider_is_template() -> None:
    settings = Settings(_env_file=None, llm_provider="template", llm_api_key=None)
    client = ConversationalLlmClient(settings)
    message = InboundMessage(request_id="req_1", user_id="u1", text="what service you offer")

    reply = asyncio.run(client.generate_reply(message))

    assert reply == build_conversational_reply(message)


@pytest.mark.asyncio
async def test_conversational_llm_calls_groq_for_help_question() -> None:
    settings = Settings(llm_provider="groq", llm_api_key="test-key")
    client = ConversationalLlmClient(settings)
    message = InboundMessage(request_id="req_1", user_id="u1", text="what service you offer")
    expected = "I help you compare prices on Jumia and Avito in Morocco."

    with patch.object(
        client,
        "_call_openai_compatible",
        new=AsyncMock(return_value=expected),
    ) as mock_call:
        reply = await client.generate_reply(message)

    assert reply == expected
    mock_call.assert_awaited_once_with(message, "groq", "en")


@pytest.mark.asyncio
async def test_orchestrator_uses_llm_for_non_shopping_message() -> None:
    settings = Settings()
    producer = FakeProducer()

    class MockConversationalLlm:
        async def generate_reply(self, message):
            return "Custom LLM help reply about Jumia and Avito."

    service = OrchestratorService(
        settings,
        agent=FakeAgent(),
        cache=EmptyCache(),
        consumer=FakeConsumer(),
        producer=producer,
        conversational_llm=MockConversationalLlm(),
    )
    message = InboundMessage(
        request_id="req_help",
        user_id="telegram_123",
        text="what service you offer",
    )

    await service.handle_message(message)

    topics = [published[0] for published in producer.published]
    assert topics == [NER_EXTRACTED, RESPONSE_OUTBOUND]
    assert "Jumia and Avito" in producer.published[1][1].message
    assert SCRAPE_TASK_ASSIGNED not in topics
