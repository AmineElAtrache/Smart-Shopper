"""HTTP LLM client with template-safe fallback semantics."""

from __future__ import annotations

import httpx

from shared.config import Settings
from shared.events.schemas import DecisionRanked


class LlmClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate_recommendation(
        self,
        event: DecisionRanked,
        fallback_message: str,
        *,
        behavior_context: dict | None = None,
    ) -> str:
        provider = self._settings.llm_provider.lower()
        if provider == "template":
            return fallback_message
        if not self._settings.llm_api_key:
            return fallback_message

        try:
            if provider == "groq":
                return await self._call_openai_compatible(event, fallback_message, behavior_context)
            if provider == "gemini":
                return await self._call_gemini(event, fallback_message, behavior_context)
        except Exception as exc:
            print(f"[generator] LLM provider {provider} failed, using template fallback: {exc}")
        return fallback_message

    async def _call_openai_compatible(
        self,
        event: DecisionRanked,
        fallback_message: str,
        behavior_context: dict | None,
    ) -> str:
        prompt = _build_prompt(event, fallback_message, behavior_context)
        async with httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds) as client:
            response = await client.post(
                f"{self._settings.llm_http_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self._settings.llm_api_key}"},
                json={
                    "model": self._settings.llm_model,
                    "messages": [
                        {"role": "system", "content": "You are Smart Shopper, a concise shopping assistant."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                },
            )
            response.raise_for_status()
            data = response.json()
            return str(data["choices"][0]["message"]["content"]).strip() or fallback_message

    async def _call_gemini(
        self,
        event: DecisionRanked,
        fallback_message: str,
        behavior_context: dict | None,
    ) -> str:
        prompt = _build_prompt(event, fallback_message, behavior_context)
        async with httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds) as client:
            response = await client.post(
                f"{self._settings.llm_http_base_url.rstrip('/')}/models/{self._settings.llm_model}:generateContent",
                params={"key": self._settings.llm_api_key},
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates") or []
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            return str(parts[0].get("text", "")).strip() if parts else fallback_message


def _build_prompt(
    event: DecisionRanked,
    fallback_message: str,
    behavior_context: dict | None = None,
) -> str:
    query = event.query.model_dump() if event.query is not None else {}
    products = [product.model_dump() for product in event.products[:3]]
    return (
        "Rewrite this shopping recommendation in a helpful, concise tone. "
        "Keep product prices, sources, scores, and URLs accurate.\n\n"
        f"Query: {query}\n"
        f"Private generator behavior context: {behavior_context or {}}\n"
        f"Products: {products}\n"
        f"Fallback response:\n{fallback_message}"
    )
