"""Tier 3: private behavioral memory for the Agent Generator.

This memory is intentionally scoped to response generation. Other agents should
not depend on it for decisioning or scraping.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from agents.agent_generator.tools.behavior_analyzer import infer_language, infer_tone
from shared.events.schemas import DecisionRanked, OutboundResponse


class BehavioralProfile(BaseModel):
    user_id: str
    tone: str = "concise"
    language: str = "en"
    response_count: int = 0
    preferred_sources: list[str] = Field(default_factory=list)
    last_interaction_at: datetime | None = None


class BehavioralMemory:
    def __init__(self, *, mongo_database: Any) -> None:
        self._profiles = mongo_database["generator_behavior_profiles"]
        self._interactions = mongo_database["generator_interactions"]

    async def ensure_indexes(self) -> None:
        await asyncio.to_thread(self._profiles.create_index, "user_id", unique=True)
        await asyncio.to_thread(self._interactions.create_index, [("user_id", 1), ("timestamp", -1)])

    async def get_profile(self, user_id: str) -> BehavioralProfile:
        document = await asyncio.to_thread(self._profiles.find_one, {"user_id": user_id})
        return (
            BehavioralProfile.model_validate(document)
            if document
            else BehavioralProfile(user_id=user_id)
        )

    async def build_generation_context(self, user_id: str) -> dict[str, Any]:
        profile = await self.get_profile(user_id)
        return {
            "tone": profile.tone,
            "language": profile.language,
            "preferred_sources": profile.preferred_sources,
            "response_count": profile.response_count,
        }

    async def record_generation(self, ranked: DecisionRanked, response: OutboundResponse) -> None:
        now = datetime.now(UTC)
        top_sources = [product.source for product in ranked.products[:3]]
        profile = await self.get_profile(ranked.user_id)
        preferred_sources = _merge_sources(profile.preferred_sources, top_sources)
        language = profile.language
        tone = profile.tone
        if ranked.user_text:
            language = infer_language(ranked.user_text)
            tone = infer_tone(ranked.user_text)
        updates = {
            "user_id": ranked.user_id,
            "tone": tone,
            "language": language,
            "response_count": profile.response_count + 1,
            "preferred_sources": preferred_sources,
            "last_interaction_at": now,
        }
        await asyncio.to_thread(
            self._profiles.update_one,
            {"user_id": ranked.user_id},
            {"$set": updates, "$setOnInsert": {"created_at": now}},
            True,
        )
        await asyncio.to_thread(
            self._interactions.insert_one,
            {
                "request_id": response.request_id,
                "user_id": response.user_id,
                "ranked_products": [product.model_dump(mode="json") for product in ranked.products[:3]],
                "message": response.message,
                "timestamp": now,
            },
        )

    async def update_style(self, user_id: str, *, tone: str | None = None, language: str | None = None) -> None:
        updates = {"last_interaction_at": datetime.now(UTC)}
        if tone:
            updates["tone"] = tone
        if language:
            updates["language"] = language
        await asyncio.to_thread(
            self._profiles.update_one,
            {"user_id": user_id},
            {"$set": updates, "$setOnInsert": {"created_at": datetime.now(UTC), "user_id": user_id}},
            True,
        )


def _merge_sources(existing: list[str], new_sources: list[str]) -> list[str]:
    merged: list[str] = []
    for source in [*existing, *new_sources]:
        if source not in merged:
            merged.append(source)
    return merged[:10]
