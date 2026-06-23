"""Tier 2: per-user shared memory.

This tier is shared across agents and stores preferences, search history,
responses, and watch metadata for a specific user.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from redis.asyncio import Redis

from shared.events.schemas import Channel, InboundMessage, OutboundResponse, ProductQuery


class UserProfile(BaseModel):
    user_id: str
    channel: Channel = Channel.TELEGRAM
    preferred_sites: list[str] = Field(default_factory=list)
    preferred_city: str | None = None
    preferred_budget: float | None = None
    preferred_currency: str = "MAD"
    language: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UserMemory:
    def __init__(
        self,
        *,
        mongo_database: Any,
        redis: Redis | None = None,
        hot_ttl_seconds: int = 24 * 60 * 60,
    ) -> None:
        self._profiles = mongo_database["user_profiles"]
        self._history = mongo_database["user_history"]
        self._watches = mongo_database["user_watches"]
        self._redis = redis
        self._hot_ttl_seconds = hot_ttl_seconds

    async def ensure_indexes(self) -> None:
        await asyncio.to_thread(self._profiles.create_index, "user_id", unique=True)
        await asyncio.to_thread(self._history.create_index, [("user_id", 1), ("timestamp", -1)])
        await asyncio.to_thread(self._watches.create_index, [("user_id", 1), ("status", 1)])

    async def get_profile(self, user_id: str) -> UserProfile:
        cached = await self._get_hot_profile(user_id)
        if cached is not None:
            return cached

        document = await asyncio.to_thread(self._profiles.find_one, {"user_id": user_id})
        profile = UserProfile.model_validate(document) if document else UserProfile(user_id=user_id)
        await self._set_hot_profile(profile)
        return profile

    async def update_preferences(
        self,
        user_id: str,
        *,
        channel: Channel | str = Channel.TELEGRAM,
        query: ProductQuery | None = None,
        language: str | None = None,
    ) -> UserProfile:
        profile = await self.get_profile(user_id)
        updates: dict[str, Any] = {
            "user_id": user_id,
            "channel": channel,
            "updated_at": datetime.now(UTC),
        }
        if query is not None:
            if query.sites:
                updates["preferred_sites"] = query.sites
            if query.city:
                updates["preferred_city"] = query.city
            if query.budget is not None:
                updates["preferred_budget"] = query.budget
            if query.currency:
                updates["preferred_currency"] = query.currency
        if language:
            updates["language"] = language

        await asyncio.to_thread(
            self._profiles.update_one,
            {"user_id": user_id},
            {"$set": updates, "$setOnInsert": {"created_at": datetime.now(UTC)}},
            True,
        )
        updated = profile.model_copy(update=updates)
        await self._set_hot_profile(updated)
        return updated

    async def apply_preferences(self, user_id: str, query: ProductQuery) -> ProductQuery:
        profile = await self.get_profile(user_id)
        return query.model_copy(
            update={
                "city": query.city or profile.preferred_city,
                "budget": query.budget if query.budget is not None else profile.preferred_budget,
                "currency": query.currency or profile.preferred_currency,
                "sites": query.sites or profile.preferred_sites,
            }
        )

    async def record_search(self, message: InboundMessage, query: ProductQuery | None = None) -> None:
        await asyncio.to_thread(
            self._history.insert_one,
            {
                "request_id": message.request_id,
                "user_id": message.user_id,
                "channel": message.channel,
                "direction": "inbound",
                "text": message.text,
                "query": query.model_dump(mode="json") if query is not None else None,
                "timestamp": datetime.now(UTC),
            },
        )
        if query is not None:
            await self.update_preferences(message.user_id, channel=message.channel, query=query)

    async def record_response(self, response: OutboundResponse) -> None:
        await asyncio.to_thread(
            self._history.insert_one,
            {
                "request_id": response.request_id,
                "user_id": response.user_id,
                "channel": response.channel,
                "direction": "outbound",
                "message": response.message,
                "timestamp": datetime.now(UTC),
            },
        )

    async def save_watch(self, user_id: str, watch: dict[str, Any]) -> None:
        document = {"user_id": user_id, **watch, "updated_at": datetime.now(UTC)}
        await asyncio.to_thread(
            self._watches.update_one,
            {"user_id": user_id, "watch_id": watch.get("watch_id")},
            {"$set": document, "$setOnInsert": {"created_at": datetime.now(UTC)}},
            True,
        )

    async def _get_hot_profile(self, user_id: str) -> UserProfile | None:
        if self._redis is None:
            return None
        value = await self._redis.get(f"user:{user_id}:profile")
        if value is None:
            return None
        raw = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        return UserProfile.model_validate(json.loads(raw))

    async def _set_hot_profile(self, profile: UserProfile) -> None:
        if self._redis is None:
            return
        await self._redis.set(
            f"user:{profile.user_id}:profile",
            profile.model_dump_json(),
            ex=self._hot_ttl_seconds,
        )
