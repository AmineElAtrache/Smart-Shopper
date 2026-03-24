"""
agents/decision_agent.py  (v2)
────────────────────────────────
Scores products from all sources.
Jumia gets a trust bonus — prices are reliable and it's the biggest MA platform.
"""
import logging, re
from agents.market_agent import NormalizedProduct

logger = logging.getLogger(__name__)

SOURCE_TRUST = {
    "jumia.ma":  1.0,
    "jumia":     1.0,
    "hmizate":   0.90,
    "avito.ma":  0.80,
    "avito":     0.80,
    "fnac":      0.85,
    "samsung":   0.95,
    "apple":     0.95,
    "nike":      0.95,
    "adidas":    0.95,
    "web":       0.50,
}


class DecisionAgent:

    def run(self, market: dict, entities: dict) -> dict:
        products = market.get("filtered") or market.get("products", [])

        if not products:
            return {
                "top_pick":     None,
                "alternatives": [],
                "reasoning":    "No products found.",
                "all_scored":   [],
            }

        price_range = market.get("price_range")
        stats       = market.get("stats", {})

        for p in products:
            p.score = self._score(p, entities, price_range, stats)

        scored = sorted(products, key=lambda x: x.score, reverse=True)
        top    = scored[0]
        alts   = scored[1:3]

        top_score = top.score if top else 0.0
        logger.info(f"Decision Agent: top pick = '{top.title if top else None}' (score={top_score:.2f})")

        return {
            "top_pick":     top,
            "alternatives": alts,
            "reasoning":    self._explain(top, entities, price_range),
            "all_scored":   scored,
        }

    def _score(self, p: NormalizedProduct, entities, price_range, stats) -> float:
        score = 0.0

        # Price fit (40 pts)
        if p.price_mad and price_range:
            mid  = (price_range["min"] + price_range["max"]) / 2
            dist = abs(p.price_mad - mid) / max(mid, 1)
            score += max(0, 1 - dist) * 40
        elif p.price_mad and stats.get("avg_mad"):
            dist = abs(p.price_mad - stats["avg_mad"]) / max(stats["avg_mad"], 1)
            score += max(0, 1 - dist) * 20
        elif p.price_mad:
            score += 10

        # Source trust (30 pts)
        src = p.source.lower()
        trust = next((v for k, v in SOURCE_TRUST.items() if k in src), 0.5)
        score += trust * 30

        # Title relevance (30 pts)
        title_l = p.title.lower()
        kws = [entities.get("product",""), entities.get("brand",""), entities.get("color","")]
        total_kw = sum(1 for k in kws if k)
        matched  = sum(1 for k in kws if k and k.lower() in title_l)
        if total_kw:
            score += (matched / total_kw) * 30

        # Discount bonus (5 pts)
        if p.discount:
            score += 5

        return round(score, 2)

    def _explain(self, p, entities, price_range) -> str:
        if not p:
            return "No suitable product found."
        parts = []
        if p.price_mad and price_range:
            lo, hi = price_range["min"], price_range["max"]
            if lo <= p.price_mad <= hi:
                parts.append(f"fits your budget ({p.price_display})")
            else:
                parts.append(f"closest to your budget ({p.price_display})")
        elif p.price_mad:
            parts.append(f"priced at {p.price_display}")
        if entities.get("brand") and entities["brand"].lower() in p.title.lower():
            parts.append(f"matches brand {entities['brand']}")
        if p.discount:
            parts.append(f"currently {p.discount} off")
        parts.append(f"from {p.source}")
        return " · ".join(parts) if parts else "Best available match."
