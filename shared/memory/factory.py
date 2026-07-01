"""Factories for constructing memory tiers from application settings."""

from __future__ import annotations

from pymongo import MongoClient
from redis.asyncio import Redis

from shared.config import Settings
from shared.memory.behavioral_memory import BehavioralMemory
from shared.memory.global_memory import GlobalMemory
from shared.memory.tier1_hooks import (
    build_price_snapshots,
    provider_domain,
    record_provider_health,
    record_query_price_samples,
    record_ranked_prices,
)
from shared.memory.user_memory import UserMemory

__all__ = [
    "create_behavioral_memory",
    "create_global_memory",
    "create_mongo_database",
    "create_redis",
    "create_user_memory",
    "build_price_snapshots",
    "provider_domain",
    "record_provider_health",
    "record_query_price_samples",
    "record_ranked_prices",
]


def create_redis(settings: Settings) -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


def create_mongo_database(settings: Settings):
    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=settings.mongo_connect_timeout_ms)
    return client[settings.mongo_db]


def create_global_memory(settings: Settings) -> GlobalMemory:
    return GlobalMemory(create_redis(settings), cache_ttl_seconds=settings.cache_ttl_seconds)


def create_user_memory(settings: Settings) -> UserMemory:
    return UserMemory(
        mongo_database=create_mongo_database(settings),
        redis=create_redis(settings),
    )


def create_behavioral_memory(settings: Settings) -> BehavioralMemory:
    return BehavioralMemory(mongo_database=create_mongo_database(settings))
