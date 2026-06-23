"""Lightweight fraud and listing-risk checks for marketplace results."""

from __future__ import annotations

from dataclasses import dataclass

from shared.events.schemas import Availability, ProductQuery, RawProduct


@dataclass(frozen=True)
class FraudSignal:
    code: str
    severity: int
    message: str


def detect_fraud_signals(product: RawProduct, query: ProductQuery) -> list[FraudSignal]:
    signals: list[FraudSignal] = []

    if query.budget and product.price < query.budget * 0.35:
        signals.append(
            FraudSignal(
                code="suspiciously_low_price",
                severity=20,
                message="Listing price is unusually low compared with the requested budget.",
            )
        )

    metadata = product.metadata or {}
    if metadata.get("mock") is True:
        return signals

    url = str(product.url).lower()
    if product.source.lower() not in url and "example.com" not in url:
        signals.append(
            FraudSignal(
                code="source_url_mismatch",
                severity=10,
                message="Listing URL does not clearly match the declared source.",
            )
        )

    if product.availability == Availability.UNKNOWN and product.rating is None:
        signals.append(
            FraudSignal(
                code="low_information_listing",
                severity=5,
                message="Listing lacks both availability and rating information.",
            )
        )

    return signals


def fraud_penalty(product: RawProduct, query: ProductQuery) -> int:
    return min(35, sum(signal.severity for signal in detect_fraud_signals(product, query)))
