"""Policy evaluation for the Governance Agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from agents.governance.rules.pii_scanner import find_pii, mask_pii
from agents.governance.rules.rate_limiter import RateLimitDecision, RateLimiter
from agents.governance.rules.robots_checker import RobotsChecker
from shared.events.schemas import GovernanceAction, GovernanceSeverity
from shared.events.topics import SCRAPE_RAW, SCRAPE_TASK_ASSIGNED


@dataclass(frozen=True)
class PolicyFinding:
    action: GovernanceAction
    severity: GovernanceSeverity
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyEvaluation:
    topic: str
    audit_payload: str
    findings: list[PolicyFinding]

    @property
    def max_severity(self) -> GovernanceSeverity:
        order = {
            GovernanceSeverity.INFO: 0,
            GovernanceSeverity.WARNING: 1,
            GovernanceSeverity.ERROR: 2,
            GovernanceSeverity.CRITICAL: 3,
        }
        return max((finding.severity for finding in self.findings), key=lambda item: order[item])

    @property
    def actions(self) -> list[GovernanceAction]:
        actions: list[GovernanceAction] = []
        for finding in self.findings:
            if finding.action not in actions:
                actions.append(finding.action)
        return actions

    @property
    def has_violation(self) -> bool:
        return any(action != GovernanceAction.AUDIT for action in self.actions)


class GovernancePolicyEngine:
    def __init__(
        self,
        *,
        user_rate_limiter: RateLimiter | None = None,
        domain_rate_limiter: RateLimiter | None = None,
        robots_checker: RobotsChecker | None = None,
        strict_robots: bool = False,
        quarantine_pii: bool = True,
    ) -> None:
        self._user_rate_limiter = user_rate_limiter
        self._domain_rate_limiter = domain_rate_limiter
        self._robots_checker = robots_checker
        self._strict_robots = strict_robots
        self._quarantine_pii = quarantine_pii

    async def evaluate(self, *, topic: str, payload: dict[str, Any]) -> PolicyEvaluation:
        payload_text = json.dumps(payload, ensure_ascii=True, default=str)
        findings = [
            PolicyFinding(
                action=GovernanceAction.AUDIT,
                severity=GovernanceSeverity.INFO,
                reason="event_audited",
            )
        ]

        pii = find_pii(payload_text)
        if pii:
            findings.append(
                PolicyFinding(
                    action=GovernanceAction.QUARANTINE if self._quarantine_pii else GovernanceAction.WARN,
                    severity=GovernanceSeverity.ERROR,
                    reason="pii_detected",
                    metadata={"pii": pii},
                )
            )

        if "raw" in payload:
            findings.append(
                PolicyFinding(
                    action=GovernanceAction.WARN,
                    severity=GovernanceSeverity.WARNING,
                    reason="malformed_event_payload",
                )
            )

        await self._evaluate_user_rate_limit(payload, findings)
        await self._evaluate_domain_rate_limit(topic, payload, findings)
        await self._evaluate_robots(topic, payload, findings)

        return PolicyEvaluation(
            topic=topic,
            audit_payload=mask_pii(payload_text),
            findings=findings,
        )

    async def _evaluate_user_rate_limit(
        self,
        payload: dict[str, Any],
        findings: list[PolicyFinding],
    ) -> None:
        if self._user_rate_limiter is None:
            return
        user_id = str(payload.get("user_id") or "").strip()
        if not user_id:
            return
        decision = await self._user_rate_limiter.check("user", user_id)
        self._append_rate_limit_finding(findings, decision, scope="user")

    async def _evaluate_domain_rate_limit(
        self,
        topic: str,
        payload: dict[str, Any],
        findings: list[PolicyFinding],
    ) -> None:
        if self._domain_rate_limiter is None or topic not in {SCRAPE_RAW, SCRAPE_TASK_ASSIGNED}:
            return
        domain = _domain_from_payload(payload)
        if domain is None:
            return
        decision = await self._domain_rate_limiter.check("domain", domain)
        self._append_rate_limit_finding(findings, decision, scope="domain")

    async def _evaluate_robots(
        self,
        topic: str,
        payload: dict[str, Any],
        findings: list[PolicyFinding],
    ) -> None:
        if self._robots_checker is None or topic != SCRAPE_RAW:
            return
        url = str(payload.get("url") or "").strip()
        if not url:
            return
        decision = await self._robots_checker.can_fetch(url)
        if not decision.allowed:
            findings.append(
                PolicyFinding(
                    action=GovernanceAction.HALT if self._strict_robots else GovernanceAction.WARN,
                    severity=GovernanceSeverity.CRITICAL if self._strict_robots else GovernanceSeverity.WARNING,
                    reason="robots_disallowed",
                    metadata={
                        "domain": decision.domain,
                        "robots_url": decision.robots_url,
                        "robots_reason": decision.reason,
                    },
                )
            )

    @staticmethod
    def _append_rate_limit_finding(
        findings: list[PolicyFinding],
        decision: RateLimitDecision,
        *,
        scope: str,
    ) -> None:
        if decision.allowed:
            return
        findings.append(
            PolicyFinding(
                action=GovernanceAction.THROTTLE,
                severity=GovernanceSeverity.WARNING,
                reason=f"{scope}_rate_limit_exceeded",
                metadata={
                    "key": decision.key,
                    "count": decision.count,
                    "limit": decision.limit,
                    "window_seconds": decision.window_seconds,
                },
            )
        )


def _domain_from_payload(payload: dict[str, Any]) -> str | None:
    url = str(payload.get("url") or "").strip()
    if url:
        domain = urlparse(url).netloc.lower()
        return domain or None
    source = str(payload.get("source") or "").strip().lower()
    return source or None
