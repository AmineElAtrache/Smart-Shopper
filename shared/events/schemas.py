"""Shared event schemas for the Kafka-based agent pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


def new_request_id() -> str:
    return f"req_{uuid4().hex}"


def utc_now() -> datetime:
    return datetime.now(UTC)


class Channel(StrEnum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    FRONTEND = "frontend"


class Currency(StrEnum):
    MAD = "MAD"
    USD = "USD"
    EUR = "EUR"


class Availability(StrEnum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"


class WatchStatus(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    EXPIRED = "expired"
    FAILED = "failed"


class GovernanceSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class GovernanceAction(StrEnum):
    AUDIT = "audit"
    WARN = "warn"
    THROTTLE = "throttle"
    HALT = "halt"
    QUARANTINE = "quarantine"

class EntityType(StrEnum):
    TARGET = "target"
    PRODUCT = "product"
    BRAND = "brand"
    PRICE = "price"
    BUDGET = "budget"
    CURRENCY = "currency"
    CITY = "city"
    COLOR = "color"
    QUALITY = "quality"
    INTENT = "intent"
    SITE = "site"


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    request_id: str = Field(default_factory=new_request_id)
    timestamp: datetime = Field(default_factory=utc_now)


class UserEvent(Event):
    user_id: str
    channel: Channel = Channel.TELEGRAM


class InboundMessage(UserEvent):
    text: str = Field(min_length=1)
    locale_hint: str | None = None

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class ExtractedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    type: EntityType
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    attributes: dict[str, str] = Field(default_factory=dict)


class NerExtracted(UserEvent):
    text: str
    entities: list[ExtractedEntity]


class ProductQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    product: str | None = None
    brand: str | None = None
    budget: float | None = Field(default=None, ge=0)
    currency: Currency = Currency.MAD
    city: str | None = None
    color: str | None = None
    quality: str | None = None
    sites: list[str] = Field(
        default_factory=lambda: [
            "jumia",
            "avito",
            "electrosalam",
            "mafiawaystore",
            "moteur",
            "mymarket",
            "ultrapc",
            "electroplanet",
            "defacto",
            "biougnach",
            "marjane",
            "decathlon",
            "mubawab",
            "ikea",
        ]
    )


class ScrapeTaskAssigned(UserEvent):
    query: ProductQuery
    watch_id: str | None = None


class RawProduct(Event):
    user_id: str | None = None
    channel: Channel = Channel.TELEGRAM
    query: ProductQuery | None = None
    source: str
    title: str
    price: float = Field(ge=0)
    currency: Currency = Currency.MAD
    url: HttpUrl | str
    availability: Availability = Availability.UNKNOWN
    seller: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScoreBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: int = Field(ge=0, le=40)
    trust: int = Field(ge=0, le=30)
    quality: int = Field(ge=0, le=20)
    availability: int = Field(ge=0, le=10)

    @property
    def total(self) -> int:
        return self.price + self.trust + self.quality + self.availability


class RankedProduct(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    title: str
    price: float
    currency: Currency = Currency.MAD
    source: str
    url: HttpUrl | str
    availability: Availability = Availability.UNKNOWN
    seller: str | None = None
    rating: float | None = None
    score: int = Field(ge=0, le=100)
    score_breakdown: ScoreBreakdown


class DecisionRanked(UserEvent):
    query: ProductQuery | None = None
    watch_id: str | None = None
    products: list[RankedProduct]


class OutboundResponse(UserEvent):
    message: str = Field(min_length=1)


class CacheWriteRequest(UserEvent):
    query: ProductQuery
    payload: str = Field(min_length=1)
    ttl_seconds: int | None = Field(default=None, ge=1)


class AmbientWatch(UserEvent):
    query: ProductQuery
    interval_minutes: int = Field(default=60, ge=15)
    expires_at: datetime | None = None
    status: WatchStatus = WatchStatus.CREATED
    last_best_price: float | None = Field(default=None, ge=0)


class PriceSnapshot(UserEvent):
    query: ProductQuery
    source: str
    title: str
    price: float = Field(ge=0)
    currency: Currency = Currency.MAD
    url: HttpUrl | str
    observed_at: datetime = Field(default_factory=utc_now)


class GovernanceEvent(Event):
    topic: str
    severity: GovernanceSeverity = GovernanceSeverity.INFO
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ErrorEvent(Event):
    source_service: str
    topic: str | None = None
    error_type: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False
