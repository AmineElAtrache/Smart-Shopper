"""
agents/orchestrator.py  (v2)
─────────────────────────────
Rich Telegram response: real prices, source badges, budget comparison, direct links.
"""
import logging, time
from agents.ner_agent      import NERAgent
from agents.research_agent import ResearchAgent
from agents.market_agent   import MarketAgent
from agents.decision_agent import DecisionAgent

logger = logging.getLogger(__name__)

SOURCE_EMOJI = {
    "jumia":  "🟠",
    "avito":  "🟢",
    "hmizate":"🔵",
    "fnac":   "🟣",
    "web":    "🌐",
}


class Orchestrator:

    def __init__(self, ner_agent: NERAgent):
        self.ner      = ner_agent
        self.research = ResearchAgent()
        self.market   = MarketAgent()
        self.decision = DecisionAgent()

    async def handle(self, query: str) -> str:
        t0 = time.perf_counter()
        logger.info(f"Orchestrator received: '{query}'")

        entities = self.ner.extract(query)
        logger.info(f"NER extracted: {entities}")

        if not any(entities.get(k) for k in ["product","brand","city","price","color"]):
            return self._no_entities_reply(query)

        research = await self.research.run(entities)

        if research["total"] == 0:
            return self._no_results_reply(entities)

        market   = self.market.run(research, entities)
        decision = self.decision.run(market, entities)

        elapsed   = time.perf_counter() - t0
        top_score = decision["top_pick"].score if decision["top_pick"] else 0.0
        logger.info(f"Orchestrator done in {elapsed:.2f}s — top score: {top_score:.2f}")

        return self._format(entities, decision, market, elapsed)

    # ─────────────────────────────────────────────────────────────────────────

    def _format(self, entities, decision, market, elapsed) -> str:
        top   = decision["top_pick"]
        alts  = decision["alternatives"]
        stats = market.get("stats", {})
        price_range = market.get("price_range")

        lines = []

        # ── What I understood ────────────────────────────────────────────────
        tags = []
        if entities.get("product"): tags.append(f"🛍 *{entities['product']}*")
        if entities.get("brand"):   tags.append(f"🏷 {entities['brand']}")
        if entities.get("color"):   tags.append(f"🎨 {entities['color']}")
        if entities.get("city"):    tags.append(f"📍 {entities['city']}")
        if entities.get("price"):   tags.append(f"💰 budget: *{entities['price']}*")

        if tags:
            lines += ["🔍 *Understood:* " + "  ·  ".join(tags), ""]

        # ── Market overview ───────────────────────────────────────────────────
        if stats:
            mn  = stats.get("min_mad", 0)
            mx  = stats.get("max_mad", 0)
            avg = stats.get("avg_mad", 0)
            cnt = stats.get("count", 0)
            lines.append(f"📊 *Market ({cnt} products found)*")
            lines.append(f"   Min: *{mn:.0f} MAD*  ·  Max: *{mx:.0f} MAD*  ·  Avg: *{avg:.0f} MAD*")

            if price_range and stats:
                budget_mid = (price_range["min"] + price_range["max"]) / 2
                if budget_mid < mn:
                    lines.append(f"   ⚠️ _Your budget ({entities.get('price')}) is below market minimum_")
                elif budget_mid > mx:
                    lines.append(f"   ✅ _Your budget covers all options_")
                else:
                    in_budget = [p for p in market.get("filtered",[]) if p.price_mad]
                    lines.append(f"   ✅ _{len(in_budget)} product(s) match your budget_")
            lines.append("")

            # Top pick — replace this block
            if top:
                src_emoji = self._src_emoji(top.source)
                lines.append(f"⭐ *Best recommendation:*")
                lines.append(f"  {src_emoji} *{top.title}*")
                lines.append(f"  💵 *{top.price_display}*" + (f"  🏷 {top.discount}" if top.discount else ""))
                lines.append(f"  🏪 {top.source}")
                lines.append(f"  _{decision['reasoning']}_")
                if top.url:
                    lines.append(f"  🔗 {top.url}")   # raw URL — no markdown brackets
                lines.append("")

            # Alternatives — replace this block
            if alts:
                lines.append("📋 *Other options:*")
                for i, p in enumerate(alts, 1):
                    src_emoji = self._src_emoji(p.source)
                    short = p.title[:55] + ("…" if len(p.title) > 55 else "")
                    price_str = f"*{p.price_display}*" if p.price_mad else "_price unknown_"
                    lines.append(f"  {i}. {src_emoji} {short}")
                    lines.append(f"     {price_str} · {p.source}")
                    if p.url:
                        lines.append(f"     🔗 {p.url}")   # raw URL — no markdown brackets
                lines.append("")

        # ── Footer ────────────────────────────────────────────────────────────
        sources_used = {p.source for p in (market.get("products") or []) if p.source}
        lines.append(f"_Sources: {', '.join(sorted(sources_used))}  ·  ⏱ {elapsed:.1f}s_")

        return "\n".join(lines)

    def _src_emoji(self, source: str) -> str:
        s = source.lower()
        for k, e in SOURCE_EMOJI.items():
            if k in s:
                return e
        return "🌐"

    def _no_entities_reply(self, query: str) -> str:
        return (
            "🤔 *I couldn't identify what you're looking for.*\n\n"
            "Try:\n"
            "  • `bghit sneakers Nike f Casablanca b 300 dh`\n"
            "  • `بغيت نشري تيشرت نايك أحمر بحوالي 200 درهم`\n"
            "  • `wach kayn laptop Samsung f Rabat b 8000 dh`"
        )

    def _no_results_reply(self, entities: dict) -> str:
        product = entities.get("product","this product")
        return (
            f"😕 No results found for *{product}*.\n\n"
            "Try:\n"
            "  • Different product name\n"
            "  • Remove city or color\n"
            "  • Broader price range"
        )
