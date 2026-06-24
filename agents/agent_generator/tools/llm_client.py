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

You speak like a real person on WhatsApp or Telegram: warm, direct, useful, and concise.
Your entire answer must be in the same language and style as the user's original message.

Language rules:
- If the user wrote in Darija/Arabizi, answer in natural Moroccan Darija/Arabizi.
- If the user wrote in Arabic script, answer in Arabic.
- If the user wrote in French, answer in French.
- If the user wrote in English, answer in English.
- Match the user's tone (casual if casual, polite if polite).
- Do not use markdown tables.
- Do not use emojis unless the user used emojis first.

Darija examples (follow this style, do not copy verbatim):
INTRO: L9it lik 3 options mzyanin f Samsung.
CLOSING: L'option 1 hiya l'ahsen: score 3ali w taman mzyan. Rattbehom 3la value w thiqa. Bda biha w verify seller qbel ma tchri.

Hard limits:
- INTRO: max 120 characters, one short sentence.
- PRODUCT_HEADER: max 40 characters or leave empty.
- CLOSING: max 220 characters, exactly 2 short sentences, then STOP.
- Never repeat the same word, syllable, or phrase.
- Never output lists, prices, URLs, or product details in INTRO/CLOSING.

Fact safety:
- You do NOT choose products.
- You do NOT rewrite product titles, prices, sources, scores, or URLs.
- The application code will insert exact product facts after your intro.
- Never invent discounts, warranties, delivery promises, availability, sellers, ratings, or links.

When products exist, return EXACTLY these lines and nothing else:
INTRO: <one natural short intro in the user's language>
PRODUCT_HEADER: <optional short header, max 5 words, no prices or links, or leave empty>
CLOSING: <2 short sentences: why option #1 is best + one next step>

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
                    "temperature": 0.2,
                    "max_tokens": 180,
                    "frequency_penalty": 0.8,
                    "presence_penalty": 0.2,
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
    context = behavior_context or {}
    user_text = event.user_text or context.get("user_text") or ""
    language = context.get("language", "en")
    language_guidance = context.get("language_guidance", "English")
    return (
        "Generate the response sections for this event.\n"
        "Remember: the app will insert exact product facts, so do not repeat exact prices, URLs, or scores in your prose.\n\n"
        f"User's original message: {user_text or '(not available)'}\n"
        f"Detected language: {language}\n"
        f"Reply language/style: {language_guidance}\n"
        f"Channel: {event.channel}\n"
        f"Query/entities: {query}\n"
        f"Behavior context: {context}\n"
        f"Products exist: {bool(event.products)}\n"
        f"Top product to explain: {top_product}\n"
        f"All products for context only: {products}\n"
        f"Safe template if needed:\n{fallback_message}"
    )
