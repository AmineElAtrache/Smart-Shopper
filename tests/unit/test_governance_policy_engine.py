from dataclasses import dataclass

import pytest

from agents.governance.policy_engine import GovernancePolicyEngine
from agents.governance.rules.rate_limiter import RateLimitDecision
from agents.governance.rules.robots_checker import RobotsDecision
from shared.events.schemas import GovernanceAction, GovernanceSeverity
from shared.events.topics import MSG_INBOUND, SCRAPE_RAW


@dataclass
class FakeRateLimiter:
    allowed: bool
    count: int = 1
    limit: int = 1

    async def check(self, scope: str, identifier: str) -> RateLimitDecision:
        return RateLimitDecision(
            allowed=self.allowed,
            key=f"rate:{scope}:{identifier}",
            count=self.count,
            limit=self.limit,
            window_seconds=60,
        )


@dataclass
class FakeRobotsChecker:
    allowed: bool

    async def can_fetch(self, url: str, *, user_agent: str = "SmartShopperBot") -> RobotsDecision:
        return RobotsDecision(
            allowed=self.allowed,
            domain="example.com",
            robots_url="https://example.com/robots.txt",
            reason="allowed" if self.allowed else "disallowed",
        )


@pytest.mark.asyncio
async def test_policy_engine_quarantines_pii_and_masks_audit_payload() -> None:
    engine = GovernancePolicyEngine(quarantine_pii=True)

    evaluation = await engine.evaluate(
        topic=MSG_INBOUND,
        payload={"user_id": "u1", "text": "call me 0612345678"},
    )

    assert GovernanceAction.QUARANTINE in evaluation.actions
    assert evaluation.max_severity == GovernanceSeverity.ERROR
    assert "[phone]" in evaluation.audit_payload
    assert "0612345678" not in evaluation.audit_payload


@pytest.mark.asyncio
async def test_policy_engine_throttles_when_user_rate_limit_is_exceeded() -> None:
    engine = GovernancePolicyEngine(user_rate_limiter=FakeRateLimiter(False, count=21, limit=20))

    evaluation = await engine.evaluate(topic=MSG_INBOUND, payload={"user_id": "u1", "text": "hi"})

    assert GovernanceAction.THROTTLE in evaluation.actions
    assert any(finding.reason == "user_rate_limit_exceeded" for finding in evaluation.findings)


@pytest.mark.asyncio
async def test_policy_engine_halts_when_strict_robots_disallows_scrape_raw() -> None:
    engine = GovernancePolicyEngine(
        robots_checker=FakeRobotsChecker(False),
        strict_robots=True,
    )

    evaluation = await engine.evaluate(
        topic=SCRAPE_RAW,
        payload={"url": "https://example.com/private/item", "source": "example"},
    )

    assert GovernanceAction.HALT in evaluation.actions
    assert evaluation.max_severity == GovernanceSeverity.CRITICAL


@pytest.mark.asyncio
async def test_policy_engine_warns_on_malformed_payload() -> None:
    engine = GovernancePolicyEngine()

    evaluation = await engine.evaluate(topic=MSG_INBOUND, payload={"raw": "not json"})

    assert GovernanceAction.WARN in evaluation.actions
    assert any(finding.reason == "malformed_event_payload" for finding in evaluation.findings)
