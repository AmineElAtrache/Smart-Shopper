"""Policy evaluation for the Governance Agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
import re
from urllib.parse import urlparse

from agents.governance.rules.pii_scanner import find_pii, mask_pii
from agents.governance.rules.rate_limiter import RateLimitDecision, RateLimiter
from agents.governance.rules.robots_checker import RobotsChecker
from shared.content_moderation import moderate_outbound_text
from shared.events.schemas import GovernanceAction, GovernanceSeverity
from shared.events.topics import RESPONSE_OUTBOUND, SCRAPE_RAW, SCRAPE_TASK_ASSIGNED

URL_RE = re.compile(r"(?P<url>https?://[^\s<>)\]\[\"']+|www\.[^\s<>)\]\[\"']+)", re.IGNORECASE)
PLACEHOLDER_DOMAINS = {
    "example.com",
    "www.example.com",
    "example.org",
    "www.example.org",
    "example.net",
    "www.example.net",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "test.com",
    "www.test.com",
    "fake.com",
    "www.fake.com",
}
PLACEHOLDER_URL_TOKENS = ("/placeholder", "/dummy", "/fake", "{", "}", "{{", "}}")


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
        content_moderation_enabled: bool = True,
    ) -> None:
        self._user_rate_limiter = user_rate_limiter
        self._domain_rate_limiter = domain_rate_limiter
        self._robots_checker = robots_checker
        self._strict_robots = strict_robots
        self._quarantine_pii = quarantine_pii
        self._content_moderation_enabled = content_moderation_enabled

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
        self._evaluate_outbound_content(topic, payload, findings)
        self._evaluate_outbound_urls(topic, payload, findings)

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

    def _evaluate_outbound_content(
        self,
        topic: str,
        payload: dict[str, Any],
        findings: list[PolicyFinding],
    ) -> None:
        if not self._content_moderation_enabled or topic != RESPONSE_OUTBOUND:
            return
        message = str(payload.get("message") or "").strip()
        if not message:
            return
        result = moderate_outbound_text(message, enabled=True)
        if result.allowed:
            return
        for finding in result.findings:
            findings.append(
                PolicyFinding(
                    action=GovernanceAction.QUARANTINE,
                    severity=GovernanceSeverity.ERROR,
                    reason=f"content_{finding.category}",
                    metadata={
                        "category": finding.category,
                        "policy_reason": finding.reason,
                        "match": finding.match,
                    },
                )
            )


    def _evaluate_outbound_urls(
        self,
        topic: str,
        payload: dict[str, Any],
        findings: list[PolicyFinding],
    ) -> None:
        if topic != RESPONSE_OUTBOUND:
            return
        message = str(payload.get("message") or "").strip()
        if not message:
            return

        fake_urls = _find_fake_outbound_urls(message)
        if not fake_urls:
            return

        findings.append(
            PolicyFinding(
                action=GovernanceAction.QUARANTINE,
                severity=GovernanceSeverity.ERROR,
                reason="fake_outbound_url",
                metadata={"urls": fake_urls},
            )
        )
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

def _extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    for match in URL_RE.finditer(text):
        url = match.group("url").rstrip(".,;:!?\"")
        if url.startswith("www."):
            url = f"https://{url}"
        urls.append(url)
    return urls


def _find_fake_outbound_urls(text: str) -> list[str]:
    fake_urls: list[str] = []
    for url in _extract_urls(text):
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()
        if domain in PLACEHOLDER_DOMAINS:
            fake_urls.append(url)
            continue
        if any(token in url.lower() for token in PLACEHOLDER_URL_TOKENS):
            fake_urls.append(url)
            continue
        if parsed.scheme not in {"http", "https"} or not domain:
            fake_urls.append(url)
    return fake_urls
