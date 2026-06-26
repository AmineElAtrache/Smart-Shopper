"""Governance Agent for audit, PII, rate-limit, robots, and policy events."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from redis.asyncio import Redis

from agents.governance.policy_engine import GovernancePolicyEngine, PolicyEvaluation
from agents.governance.rules.rate_limiter import RateLimiter
from agents.governance.rules.robots_checker import RobotsChecker
from shared.config import Settings, get_settings
from shared.events.kafka import KafkaEventProducer
from shared.events.schemas import GovernanceEvent
from shared.events.topics import ALL_TOPICS, GOV_AUDIT, GOV_VIOLATION
from shared.runtime import HealthServer


class GovernanceAgent:
    def __init__(
        self,
        settings: Settings,
        *,
        producer: KafkaEventProducer | None = None,
        policy_engine: GovernancePolicyEngine | None = None,
        redis: Redis | None = None,
    ) -> None:
        self._settings = settings
        self._producer = producer or KafkaEventProducer(
            settings.kafka_bootstrap_servers,
            client_id="governance-agent",
        )
        self._redis = redis
        self._owns_redis = redis is None and policy_engine is None
        self._policy_engine = policy_engine or self._build_policy_engine(redis)

    async def start(self) -> None:
        await self._producer.start()

    async def stop(self) -> None:
        await self._producer.stop()
        if self._owns_redis and self._redis is not None:
            await self._redis.aclose()

    async def audit_payload(self, *, topic: str, payload: dict[str, Any]) -> PolicyEvaluation:
        evaluation = await self._policy_engine.evaluate(topic=topic, payload=payload)
        event = GovernanceEvent(
            topic=topic,
            severity=evaluation.max_severity,
            message="Event audited by Governance Agent.",
            metadata={
                "actions": [action.value for action in evaluation.actions],
                "findings": [
                    {
                        "action": finding.action.value,
                        "severity": finding.severity.value,
                        "reason": finding.reason,
                        "metadata": finding.metadata,
                    }
                    for finding in evaluation.findings
                ],
                "payload": evaluation.audit_payload,
            },
        )
        await self._producer.publish(GOV_AUDIT, event, key=event.request_id)

        if evaluation.has_violation:
            violation = GovernanceEvent(
                topic=topic,
                severity=evaluation.max_severity,
                message="Governance policy violation detected.",
                metadata={
                    "actions": [action.value for action in evaluation.actions if action.value != "audit"],
                    "findings": [
                        {
                            "action": finding.action.value,
                            "severity": finding.severity.value,
                            "reason": finding.reason,
                            "metadata": finding.metadata,
                        }
                        for finding in evaluation.findings
                        if finding.action.value != "audit"
                    ],
                },
            )
            await self._producer.publish(GOV_VIOLATION, violation, key=violation.request_id)
        return evaluation

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

    def _build_policy_engine(self, redis: Redis | None) -> GovernancePolicyEngine:
        redis_client = redis or Redis.from_url(self._settings.redis_url, decode_responses=False)
        self._redis = redis_client
        return GovernancePolicyEngine(
            user_rate_limiter=RateLimiter(
                redis_client,
                limit=self._settings.user_rate_limit_per_minute,
                window_seconds=60,
            ),
            domain_rate_limiter=RateLimiter(
                redis_client,
                limit=self._settings.domain_rate_limit_per_minute,
                window_seconds=60,
            ),
            robots_checker=RobotsChecker(redis_client),
            strict_robots=self._settings.governance_strict_robots,
            quarantine_pii=self._settings.governance_quarantine_pii,
            content_moderation_enabled=self._settings.governance_content_moderation_enabled,
        )


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
