"""LLM-backed conversational replies for non-shopping inbound messages."""

from __future__ import annotations

import re

import httpx

from agents.agent_generator.tools.behavior_analyzer import LANGUAGE_GUIDANCE, infer_language
from agents.agent_generator.tools.llm_client import (
    OPENAI_COMPATIBLE_PROVIDERS,
    PROVIDER_DEFAULT_BASE_URLS,
)
from agents.agent_generator.tools.text_safety import is_usable_prose, sanitize_llm_prose
from agents.orchestrator.tools.conversational_reply import (
    build_conversational_reply,
    is_help_question,
)
from shared.config import Settings
from shared.events.schemas import InboundMessage

GENERAL_REPLY_PREFIX = re.compile(r"^GENERAL_REPLY:\s*", re.IGNORECASE)

_BAD_DARIJA_PHRASES = re.compile(
    r"\b("
    r"kifach t-jaweb|kifach t jaweb|9alaykum|salaykum|alaykum|"
    r"kaydur had lboot[,\?]|kaydur had l-boot[,\?]"
    r")\b",
    re.IGNORECASE,
)
_WRONG_LANGUAGE_OPENING = re.compile(
    r"^(?:hello|hi|hey|bonjour|salut|as-salamu|assalamu)\b",
    re.IGNORECASE,
)

_LANGUAGE_LOCK = """
Language rules (critical):
- Reply in ONE language only: {language_name}
- Do NOT mix languages in the same answer
- Do NOT open with a greeting in a different language
- Match the user's tone: casual if casual, polite if polite
"""

_SMALLTALK_RULES = """
Small-talk rules:
- Greetings → greet back briefly, then offer help
- Do NOT treat greeting words as product names
- Do NOT ask for budget or city unless the user asked to search for a product
"""

CONVERSATIONAL_SYSTEM_PROMPT = (
    """You are Smart Shopper (Dalil Souq), a Moroccan shopping assistant on Telegram.

What you do:
- Help users search and compare products across Moroccan marketplaces such as Jumia, Avito, Electroplanet, Marjane, and IKEA
- Users tell you what they want, their budget, and optionally their city
- You run a product search only when they give a concrete shopping request

How to reply:
- If they greet you, greet back briefly
- If they ask what you do or what services you offer, explain clearly in 2-4 sentences
- Do NOT invent prices, product names, URLs, or listings
- Keep answers concise and friendly like WhatsApp or Telegram
- Return plain conversational text only
"""
    + _LANGUAGE_LOCK.format(language_name="English")
    + _SMALLTALK_RULES
)

CONVERSATIONAL_FR_SYSTEM_PROMPT = (
    """Tu es Smart Shopper (Dalil Souq), assistant shopping marocain sur Telegram.

Ce que tu fais:
- Tu aides à chercher et comparer des produits sur Jumia, Avito, Electroplanet, Marjane, IKEA et d'autres sites marocains
- L'utilisateur te dit ce qu'il cherche, son budget, et éventuellement sa ville

Comment répondre:
- S'il te salue, réponds brièvement et propose ton aide
- S'il demande ce que tu fais ou quels services tu offres, explique en 2-4 phrases
- Ne invente jamais de prix, produits, URLs ou annonces
- Réponse courte, naturelle, comme sur WhatsApp
"""
    + _LANGUAGE_LOCK.format(language_name="French")
    + _SMALLTALK_RULES
)

CONVERSATIONAL_DARIJA_SYSTEM_PROMPT = (
    """Nta Smart Shopper (Dalil Souq), assistant dyal shopping f Telegram l-mgharibi.

Chno katdir:
- Kat3awen l-user y9leb w y-qaren produits mn Jumia, Avito, Electroplanet, Marjane, IKEA, w sites khrin
- L-user kaygoul chno bghiti, ch7al l-mizaniya, w ila bghiti l-mdina

Kifach t-jaweb (Mohim bzaf):
- Jaweb ghir b Darija Maghribiya f Arabizi (Latin b 3, 7, 9)
- Mamno3 t-bda b English wla l-3arabiya l-fos7a ila l-user kteb b Darija
- Mamno3 t-st3mel kalimat ma3nawhomch: "kifach t-jaweb", "9alaykum", "salaykum"
- Ila salam (slm, labas, kidayer, cv) → "Lbas 3lik!" w 9ol lih kifach ymken n3awno
- Ila s9al chno katdir / chnahoma les services / chno kaydur had lboot → fassar l-services b 2-3 jmal wade7in

Amthila (itba3 style, ma t-nqlch nafs l-jmal):
User: slm cv kidayer lbs 3lik
Reply: Lbas 3lik! Ana Smart Shopper, hna bach n3awnek t9leb 3la produits. Chno bghiti?

User: chnahoma les services li kadero
Reply: Ana kan3awen n9leb 3la produits f Jumia, Avito, Electroplanet, Marjane w IKEA. Goul liya chno bghiti w ch7al l-mizaniya.

User: chno kaydur had lboot
Reply: Had l-boot hwa Smart Shopper, assistant dyal shopping f l-Maghrib. Kan9leb lik 3la produits w kanwerrekh lik l-khityarat; nta li tkhtar.

Ma t-hazch taman, produit, wla links. Jawb qssir w natural b7al WhatsApp.
"""
    + _LANGUAGE_LOCK.format(language_name="Moroccan Darija Arabizi")
    + _SMALLTALK_RULES
)

CONVERSATIONAL_AR_SYSTEM_PROMPT = (
    """أنت Smart Shopper (Dalil Souq)، مساعد تسوق مغربي على Telegram.

ما الذي تفعله:
- تساعد المستخدمين على البحث عن المنتجات ومقارنتها في Jumia وAvito ومتاجر مغربية أخرى

أجب بالعربية الفصحى فقط، باختصار وود، في 2-4 جمل.
لا تختلق أسعاراً أو روابط أو منتجات.
"""
    + _LANGUAGE_LOCK.format(language_name="Modern Standard Arabic")
    + _SMALLTALK_RULES
)


def conversational_system_prompt_for_language(language: str) -> str:
    if language == "darija":
        return CONVERSATIONAL_DARIJA_SYSTEM_PROMPT
    if language == "ar":
        return CONVERSATIONAL_AR_SYSTEM_PROMPT
    if language == "fr":
        return CONVERSATIONAL_FR_SYSTEM_PROMPT
    return CONVERSATIONAL_SYSTEM_PROMPT


def build_conversational_user_prompt(text: str, language: str) -> str:
    language_name = LANGUAGE_GUIDANCE.get(language, "English")
    intent = "help_question" if is_help_question(text) else "greeting_or_chat"
    intent_note = {
        "help_question": "The user asks what you do or what services you offer. Explain clearly.",
        "greeting_or_chat": "The user greets you or chats. Greet back briefly and offer help.",
    }[intent]
    return (
        f"Detected user language: {language_name}\n"
        f"Reply in {language_name} ONLY for the entire answer.\n"
        f"Intent: {intent_note}\n"
        f"User message:\n{text.strip()}"
    )


def is_valid_conversational_reply(text: str, language: str) -> bool:
    if not is_usable_prose(text, max_length=500):
        return False
    if language == "darija":
        if _WRONG_LANGUAGE_OPENING.search(text):
            return False
        if _BAD_DARIJA_PHRASES.search(text):
            return False
    if language == "en" and _WRONG_LANGUAGE_OPENING.search(text) and text.lower().startswith(("bonjour", "salut")):
        return False
    if language == "fr" and text.lower().startswith(("hello", "hi ", "hey ")):
        return False
    return True


def clean_conversational_output(text: str) -> str:
    cleaned = sanitize_llm_prose(text, max_length=500)
    cleaned = GENERAL_REPLY_PREFIX.sub("", cleaned).strip()
    return cleaned


class ConversationalLlmClient:
    """Generate natural chat replies; falls back to templates when LLM is unavailable."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate_reply(self, message: InboundMessage) -> str:
        fallback = build_conversational_reply(message)
        provider = self._settings.llm_provider.lower().strip()
        api_key = (self._settings.llm_api_key or "").strip()
        if provider == "template" or not api_key:
            return fallback

        language = infer_language(message.text or "")

        try:
            if provider in OPENAI_COMPATIBLE_PROVIDERS:
                reply = await self._call_openai_compatible(message, provider, language)
            elif provider == "gemini":
                reply = await self._call_gemini(message, provider, language)
            else:
                print(f"[orchestrator] unsupported conversational LLM provider {provider}")
                return fallback
            cleaned = clean_conversational_output(reply)
            if not is_valid_conversational_reply(cleaned, language):
                print(f"[orchestrator] conversational LLM reply rejected, using template fallback")
                return fallback
            return cleaned
        except Exception as exc:
            print(f"[orchestrator] conversational LLM failed, using template fallback: {exc}")
            return fallback

    async def _call_openai_compatible(
        self,
        message: InboundMessage,
        provider: str,
        language: str,
    ) -> str:
        system_prompt = conversational_system_prompt_for_language(language)
        user_prompt = build_conversational_user_prompt(message.text or "", language)
        is_darija = language == "darija"
        async with httpx.AsyncClient(timeout=self._settings.llm_timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url(provider).rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self._settings.llm_api_key}"},
                json={
                    "model": self._settings.llm_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.35 if is_darija else 0.2,
                    "max_tokens": 200,
                    "frequency_penalty": 0.6,
                    "presence_penalty": 0.4,
                },
            )
            response.raise_for_status()
            data = response.json()
            return str(data["choices"][0]["message"]["content"]).strip()

    async def _call_gemini(
        self,
        message: InboundMessage,
        provider: str,
        language: str,
    ) -> str:
        system_prompt = conversational_system_prompt_for_language(language)
        user_prompt = build_conversational_user_prompt(message.text or "", language)
        prompt = f"{system_prompt}\n\n{user_prompt}"
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
            return str(parts[0].get("text", "")).strip()

    def _base_url(self, provider: str) -> str:
        configured = self._settings.llm_http_base_url.strip()
        if configured and configured != "http://localhost:8081":
            return configured
        return PROVIDER_DEFAULT_BASE_URLS.get(provider, configured)
