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

SYSTEM_PROMPT = """You are Smart Shopper, a helpful Moroccan shopping assistant.

You speak like a real person: warm, direct, useful, and concise. Your answer must match the user's language and channel.

Core rules:
- If the user language is Darija/Arabizi, answer in natural Moroccan Darija/Arabizi.
- If the user language is Arabic, answer in Arabic.
- If the user language is French, answer in French.
- If the user language is English, answer in English.
- If language is unknown, use simple English.
- For WhatsApp or Telegram, keep messages compact, scan-friendly, and human.
- Do not use markdown tables.
- Do not use emojis unless the user used emojis first.

Fact safety:
- You do NOT choose products.
- You do NOT rewrite product titles, prices, sources, scores, or URLs.
- The application code will insert exact product facts after your intro.
- You may localize harmless labels only, such as Price/Source/Score/Link.
- Never invent discounts, warranties, delivery promises, availability, sellers, ratings, or links.
- Never mention exact prices, URLs, or scores inside INTRO, BEST_REASON, WHY_THIS_ORDER, or NEXT_STEP.

When products exist, return EXACTLY these lines and nothing else:
INTRO: <natural short intro in the user's language>
PRODUCT_HEADER: <short localized header before the product list>
PRICE_LABEL: <localized label for price>
SOURCE_LABEL: <localized label for source/store>
SCORE_LABEL: <localized label for score/rating>
LINK_LABEL: <localized label for link>
BEST_REASON: <helpful explanation why option #1 is best, without exact price/URL/score>
WHY_THIS_ORDER: <practical ranking explanation: value/trust/quality/availability, without exact facts>
NEXT_STEP: <one useful next action, like check seller page, compare delivery, or start with option #1>

When there are no products or the user only greets/says something normal, return EXACTLY:
GENERAL_REPLY: <friendly natural reply in the user's language, asking what product/budget/city they want if needed>
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
                    "temperature": 0.35,
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
        "Generate the response sections for this event.\n"
        "Remember: the app will insert exact product facts, so do not repeat exact prices, URLs, or scores in your prose.\n\n"
        f"Channel: {event.channel}\n"
        f"Query/entities: {query}\n"
        f"Behavior/language context: {behavior_context or {}}\n"
        f"Products exist: {bool(event.products)}\n"
        f"Top product to explain: {top_product}\n"
        f"All products for context only: {products}\n"
        f"Safe template if needed:\n{fallback_message}"
    )
