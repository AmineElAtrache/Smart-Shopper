"""Governance Agent for audit, PII, and policy violation events."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from agents.governance.rules.pii_scanner import find_pii, mask_pii
from shared.config import Settings, get_settings
from shared.events.kafka import KafkaEventProducer
from shared.events.schemas import GovernanceEvent, GovernanceSeverity
from shared.events.topics import ALL_TOPICS, GOV_AUDIT, GOV_VIOLATION
from shared.runtime import HealthServer


class GovernanceAgent:
    def __init__(
        self,
        settings: Settings,
        *,
        producer: KafkaEventProducer | None = None,
    ) -> None:
        self._settings = settings
        self._producer = producer or KafkaEventProducer(
            settings.kafka_bootstrap_servers,
            client_id="governance-agent",
        )

    async def start(self) -> None:
        await self._producer.start()

    async def stop(self) -> None:
        await self._producer.stop()

    async def audit_payload(self, *, topic: str, payload: dict[str, Any]) -> None:
        payload_text = json.dumps(payload, ensure_ascii=True, default=str)
        pii_findings = find_pii(payload_text)
        severity = GovernanceSeverity.WARNING if pii_findings else GovernanceSeverity.INFO
        event = GovernanceEvent(
            topic=topic,
            severity=severity,
            message="PII detected in event payload." if pii_findings else "Event audited.",
            metadata={
                "pii": pii_findings,
                "payload": mask_pii(payload_text),
            },
        )
        await self._producer.publish(GOV_AUDIT, event, key=event.request_id)
        if pii_findings:
            violation = GovernanceEvent(
                topic=topic,
                severity=GovernanceSeverity.ERROR,
                message="Governance violation: sensitive data should be masked before storage.",
                metadata={"pii": pii_findings},
            )
            await self._producer.publish(GOV_VIOLATION, violation, key=violation.request_id)

    async def run_forever(self) -> None:
        from aiokafka import AIOKafkaConsumer

        topics = tuple(topic for topic in ALL_TOPICS if topic not in {GOV_AUDIT, GOV_VIOLATION})
        consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            group_id=self._settings.governance_group_id,
            client_id=self._settings.kafka_client_id,
            auto_offset_reset="earliest",
        )
        await self.start()
        await consumer.start()
        try:
            async for message in consumer:
                try:
                    payload = json.loads(message.value.decode("utf-8"))
                except Exception:
                    payload = {"raw": message.value.decode("utf-8", errors="replace")}
                await self.audit_payload(topic=message.topic, payload=payload)
        finally:
            await consumer.stop()
            await self.stop()


async def main() -> None:
    settings = get_settings()
    health = HealthServer(host=settings.metrics_host, port=settings.metrics_port)
    await health.start()
    try:
        await GovernanceAgent(settings).run_forever()
    finally:
        await health.stop()


if __name__ == "__main__":
    asyncio.run(main())
