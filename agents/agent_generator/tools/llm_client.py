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

SYSTEM_PROMPT = """You are Smart Shopper's final response writer.

Your job is NOT to choose products and NOT to rewrite product facts.
The system code will print exact product titles, prices, sources, scores, and links.
You only write a short intro and a short best-choice explanation.

Language rules:
- Reply in the same language/style as the user when it is known from context.
- If the user writes Darija/Arabizi, use simple Moroccan Darija/Arabizi.
- If the user writes French, use French.
- If the user writes English, use English.
- If language is unknown, use simple English.

Channel rules:
- For WhatsApp or Telegram, keep it compact and mobile-friendly.
- No markdown tables.
- No long paragraphs.
- No emojis unless the user uses emojis first.

Safety rules:
- Do not invent products, prices, discounts, stock state, warranties, sources, scores, or URLs.
- Do not mention product prices or links in your answer sections.
- Do not add legal/medical/financial advice.
- Do not ask a follow-up question unless there are no products.

Output format must be exactly:
INTRO: <one short sentence>
BEST_REASON: <one short sentence explaining why product #1 is the best among the listed options>
"""


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
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.15,
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
        prompt = f"{SYSTEM_PROMPT}\n\n{_build_prompt(event, fallback_message, behavior_context)}"
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
    top_product = event.products[0].model_dump() if event.products else {}
    return (
        "Write only INTRO and BEST_REASON for this shopping result.\n"
        "The app will add the exact product list after INTRO.\n"
        "Do not copy prices, URLs, or scores into your sections.\n\n"
        f"Channel: {event.channel}\n"
        f"Query/entities: {query}\n"
        f"Behavior/language context: {behavior_context or {}}\n"
        f"Top product to explain: {top_product}\n"
        f"All listed products for context only: {products}\n"
        f"Safe template if needed:\n{fallback_message}"
    )
