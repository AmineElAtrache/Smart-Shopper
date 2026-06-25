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

Neutrality rules (critical):
- Present options without pushing the user toward any product.
- Do NOT recommend, rank as "best", or tell the user what to buy.
- Do NOT say first option is best, top pick, start with, or open this link first.
- Explain listing criteria only; let the user decide.
- Do NOT say "no bias", "neutral", "without favoring", "no recommendation", or similar disclaimers.
- Stay impartial through tone and facts, not by announcing impartiality.

Language rules:
- If the user wrote in Arabic script, answer in Arabic.
- If the user wrote in French, answer in French.
- If the user wrote in English, answer in English.
- Match the user's tone (casual if casual, polite if polite).
- Do not use markdown tables.
- Do not use emojis unless the user used emojis first.

Hard limits:
- INTRO: max 120 characters, one short sentence.
- PRODUCT_HEADER: max 40 characters or leave empty.
- CLOSING: max 220 characters, exactly 2 short sentences.
- Never repeat the same word, syllable, or phrase.
- Never output lists, prices, URLs, or product details in INTRO/CLOSING.

Fact safety:
- You do NOT choose products.
- You do NOT rewrite product titles, prices, sources, scores, or URLs.
- The application code will insert exact product facts after your intro.
- Never invent discounts, warranties, delivery promises, availability, sellers, ratings, or links.

When products exist, return EXACTLY these lines and nothing else:
INTRO: <short intro: options found for the search>
PRODUCT_HEADER: <optional short header, max 5 words, no prices or links, or leave empty>
CLOSING: <2 sentences: how the list is ordered + invite the user to review and choose>

When there are no products or the user only greets/says something normal, return EXACTLY:
GENERAL_REPLY: <friendly natural reply in the user's language, asking what product/budget/city they want if needed>
"""

DARIJA_SYSTEM_PROMPT = """Nta Smart Shopper, assistant dyal shopping l-mgharibi.

Khassk t-jaweb ghir b Darija Maghribiya f Arabizi (Latin script b 3, 7, 9).
Mamno3 t-khrej l-Fransiz wla l-Ingliz khla l-ism dyal l-produit wla l-ma7all (Jumia, Samsung...).

Neutrality (mohim bzaf):
- 3tih l-khityarat bla ma t-favori wahda f l-klam.
- Ma t9olch "ahsen", "l-ula hiya l-ahsen", "bda biha", "chri", wla "option 1".
- Fassar ghir kifach rattabti l-lista; khalli l-user y-khtar.
- Ma t9olch "bla tafdil", "neutral", "la tawsiya", "bla bias", wla ay disclaimer 3la impartiality.

Klimat Darija li khassk tst3mel:
l9it, hahuma, khityar, khityarat, taman, lien, kayna, chouf, qra, karar, rattabt, 3la, w, d, b, f, thiqa, qima, wjoud, daba, chno, afak, 3tini, n9leb, tartib, ma3lomat.

Mamno3 b serah: verify, seller, delivery, availability, stock, best, choice, option, meilleur, a7sen, recommend, top, buy, found, ranked, value, trust, quality, open, link, phone, budget, mzyanin, tafdil, bias, tawsiya, neutral, favori.

Hard limits:
- INTRO: jmla wa7da, max 120 characters.
- PRODUCT_HEADER: max 40 characters wla khaliha khawya.
- CLOSING: juj jmal, max 220 characters.
- Ma t3awedch nafs l-kelma wla l-mora.

Fact safety:
- Ma tbeddelch titles, prices, sources, scores, wla URLs.
- L-code ghadi y-zid l-ma3lomat exact men ba3d INTRO.
- Ma t-hazch taman, URL, wla score f INTRO/CLOSING.

Amthila (ma t-nqlch nafs l-jmal verbatim):
INTRO: Hahuma 3 khityarat li lqit lik f Samsung.
PRODUCT_HEADER: Tafasil dyal kol khityar:
CLOSING: Tartib dyal l-lista kay7seb taman w thiqa. Khtar li bghiti mn ba3d ma t-qra.

Style:
- Jaweb b Darija natural b7al WhatsApp.
- Beddel l-kelmat f kol message; ma t-nqlch nafs CLOSING f kol jawb.
- I3tas b chi kelma mn message dyal l-user ila ma kaynch mochkil (bghit, kan9leb, budget, mdina...).
- Khalli l-jawb wa7ed, m-fhom, w objective bla ma t-3l9 3la bias wla neutrality.

Mni kayn products, rje3 ghir had l-lines:
INTRO: <intro b Darija>
PRODUCT_HEADER: <header qssir wla khawi>
CLOSING: <juj jmal: kifach l-lista m-rattba + d3i l-user y-chouf w y-khtar>

Mni makaynch products wla greeting:
GENERAL_REPLY: <jawb b Darija, salam w 9ol lih chno bghiti w ch7al l-mizaniya>
"""


def system_prompt_for_language(language: str) -> str:
    if language == "darija":
        return DARIJA_SYSTEM_PROMPT
    return SYSTEM_PROMPT


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
        language = str((behavior_context or {}).get("language", "en"))
        system_prompt = system_prompt_for_language(language)
        is_darija = language == "darija"
        async with httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url(provider).rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self._settings.llm_api_key}"},
                json={
                    "model": self._settings.llm_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.45 if is_darija else 0.2,
                    "max_tokens": 280 if is_darija else 180,
                    "frequency_penalty": 0.6 if is_darija else 0.8,
                    "presence_penalty": 0.3 if is_darija else 0.2,
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
        language = str((behavior_context or {}).get("language", "en"))
        system_prompt = system_prompt_for_language(language)
        prompt = f"{system_prompt}\n\n{_build_prompt(event, fallback_message, behavior_context)}"
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
    darija_note = ""
    if language == "darija":
        darija_note = (
            "IMPORTANT: Reply 100% in Moroccan Darija Arabizi only. "
            "Do not mix French or English words. "
            "Write naturally like WhatsApp, vary your wording, and reflect the user's request.\n"
        )
    return (
        f"{darija_note}"
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
