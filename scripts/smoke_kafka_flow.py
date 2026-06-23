"""Publish one inbound request and wait for a response.outbound event."""

from __future__ import annotations

import asyncio

from shared.config import get_settings
from shared.events.kafka import KafkaEventConsumer, KafkaEventProducer
from shared.events.schemas import Channel, InboundMessage, OutboundResponse
from shared.events.topics import MSG_INBOUND, RESPONSE_OUTBOUND


async def run_smoke_test(timeout_seconds: float = 60.0) -> OutboundResponse:
    settings = get_settings()
    producer = KafkaEventProducer(
        settings.kafka_bootstrap_servers,
        client_id=f"{settings.kafka_client_id}-smoke-producer",
    )
    consumer = KafkaEventConsumer(
        RESPONSE_OUTBOUND,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="smart-shopper-smoke-test",
        client_id=f"{settings.kafka_client_id}-smoke-consumer",
    )
    inbound = InboundMessage(
        user_id="telegram_000",
        channel=Channel.TELEGRAM,
        text="Bghit Samsung phone b 3000 dh",
    )

    await producer.start()
    await consumer.start()
    try:
        print(f"Publishing msg.inbound request_id={inbound.request_id} to {settings.kafka_bootstrap_servers}")
        await producer.publish(MSG_INBOUND, inbound, key=inbound.request_id)
        print(f"Waiting up to {timeout_seconds:.0f}s for response.outbound request_id={inbound.request_id}")

        async def wait_for_response() -> OutboundResponse:
            async for event in consumer.events(OutboundResponse):
                if event.request_id == inbound.request_id:
                    return event
            raise RuntimeError("response consumer stopped before receiving smoke response")

        return await asyncio.wait_for(wait_for_response(), timeout=timeout_seconds)
    finally:
        await consumer.stop()
        await producer.stop()


async def main() -> None:
    response = await run_smoke_test()
    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
