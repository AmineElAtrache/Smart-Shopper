"""HTTP LLM client with template-safe fallback semantics."""

from __future__ import annotations

import httpx

from shared.config import Settings
from shared.events.schemas import DecisionRanked

OPENAI_COMPATIBLE_PROVIDERS = {"groq", "openai", "openai-compatible", "openai_compatible"}
PROVIDER_DEFAULT_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
}


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
        provider = self._settings.llm_provider.lower().strip()
        if provider == "template":
            return fallback_message
        if not self._settings.llm_api_key:
            return fallback_message

        try:
            if provider in OPENAI_COMPATIBLE_PROVIDERS:
                return await self._call_openai_compatible(
                    provider,
                    event,
                    fallback_message,
                    behavior_context,
                )
            if provider == "gemini":
                return await self._call_gemini(provider, event, fallback_message, behavior_context)
            print(f"[generator] unsupported LLM provider {provider}, using template fallback")
        except Exception as exc:
            print(f"[generator] LLM provider {provider} failed, using template fallback: {exc}")
        return fallback_message

    async def _call_openai_compatible(
        self,
        provider: str,
        event: DecisionRanked,
        fallback_message: str,
        behavior_context: dict | None,
    ) -> str:
        prompt = _build_prompt(event, fallback_message, behavior_context)
        async with httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url(provider).rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self._settings.llm_api_key}"},
                json={
                    "model": self._settings.llm_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are Smart Shopper. Write concise shopping recommendations. "
                                "Never invent products, prices, sources, scores, or URLs."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                },
            )
            response.raise_for_status()
            data = response.json()
            return str(data["choices"][0]["message"]["content"]).strip() or fallback_message

    async def _call_gemini(
        self,
        provider: str,
        event: DecisionRanked,
        fallback_message: str,
        behavior_context: dict | None,
    ) -> str:
        prompt = _build_prompt(event, fallback_message, behavior_context)
        async with httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url(provider).rstrip('/')}/models/{self._settings.llm_model}:generateContent",
                params={"key": self._settings.llm_api_key},
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates") or []
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            return str(parts[0].get("text", "")).strip() if parts else fallback_message

    def _base_url(self, provider: str) -> str:
        configured = self._settings.llm_http_base_url.strip()
        if configured and configured != "http://localhost:8081":
            return configured
        return PROVIDER_DEFAULT_BASE_URLS.get(provider, configured)


def _build_prompt(
    event: DecisionRanked,
    fallback_message: str,
    behavior_context: dict | None = None,
) -> str:
    query = event.query.model_dump() if event.query is not None else {}
    products = [product.model_dump() for product in event.products[:3]]
    return (
        "Rewrite the fallback response into a helpful final shopping answer.\n"
        "Hard rules:\n"
        "- Use only the products listed below.\n"
        "- Keep every listed product price, source, score, and URL exactly visible.\n"
        "- Do not add products, claims, discounts, stock status, or URLs that are not in the data.\n"
        "- If behavior context asks for tone/language, adapt style only, not facts.\n\n"
        f"Query: {query}\n"
        f"Private generator behavior context: {behavior_context or {}}\n"
        f"Products: {products}\n"
        f"Fallback response:\n{fallback_message}"
    )
