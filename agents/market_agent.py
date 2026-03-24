"""
agents/market_agent.py  (v2)
─────────────────────────────
- Collects from all 3 sources (DDG, Jumia, Avito)
- Strictly filters by user's stated price — not just ±10%
- Clearly labels which source each product came from
- Deduplicates by title similarity
"""
import logging, re
from dataclasses import dataclass
from typing import Optional
from scrapers.jumia import ProductResult

logger = logging.getLogger(__name__)


@dataclass
class NormalizedProduct:
    title:         str
    price_mad:     Optional[float]
    price_display: str
    source:        str
    url:           str
    discount:      Optional[str] = None
    score:         float = 0.0


class MarketAgent:

    def run(self, research: dict, entities: dict) -> dict:
        # Collect all results from all sources
        all_raw: list[ProductResult] = (
            research.get("jumia", []) +   # Jumia first — real prices
            research.get("avito", []) +
            research.get("ddg",   []) +
            research.get("google", [])    # fallback alias
        )

        # Deduplicate and normalize
        normalized = []
        seen = set()
        for item in all_raw:
            key = item.title.lower()[:45]
            if key in seen:
                continue
            seen.add(key)
            price_mad = self._parse_price(item.price)
            normalized.append(NormalizedProduct(
                title         = item.title,
                price_mad     = price_mad,
                price_display = self._clean_price_display(item.price),
                source        = item.source,
                url           = item.url,
                discount      = item.extra.get("discount") if item.extra else None,
            ))

        # Parse user's budget
        price_range = self._parse_user_price(entities.get("price"))

        # Split: has price vs no price
        with_price    = sorted([p for p in normalized if p.price_mad], key=lambda x: x.price_mad)
        without_price = [p for p in normalized if not p.price_mad]

        # Filter by user budget (strict: within range)
        if price_range and with_price:
            in_range = [
                p for p in with_price
                if price_range["min"] <= p.price_mad <= price_range["max"]
            ]
            # If nothing in range, show closest ones instead
            filtered = in_range if in_range else sorted(
                with_price,
                key=lambda p: abs(p.price_mad - (price_range["min"] + price_range["max"]) / 2)
            )[:6]
        else:
            filtered = with_price[:6] + without_price[:2]

        # Stats
        prices = [p.price_mad for p in with_price]
        stats  = {}
        if prices:
            stats = {
                "min_mad": min(prices),
                "max_mad": max(prices),
                "avg_mad": sum(prices) / len(prices),
                "count":   len(prices),
            }
            if price_range:
                stats["user_budget"] = price_range

        logger.info(
            f"Market: {len(normalized)} total, {len(with_price)} with price, "
            f"{len(filtered)} in range"
        )

        return {
            "products":    with_price + without_price,
            "price_range": price_range,
            "filtered":    filtered,
            "stats":       stats,
        }

    # ── Price parsing ─────────────────────────────────────────────────────────

    def _parse_price(self, s: str) -> Optional[float]:
        if not s:
            return None

        s = s.replace("\xa0", " ").strip()
        s = re.sub(r"(?i)(dhs|dh|mad|درهم)", " ", s)
        s = re.sub(r"\(.*?\)", " ", s)
        s = re.sub(r"\d+%", " ", s)
        # Comma as thousands separator: "6,599" → "6599"
        s = re.sub(r"(\d),(\d{3})", r"\1\2", s)

        m = re.search(r"\d+\.?\d*", s)
        if not m:
            return None

        val = float(m.group(0))

        lower = s.lower()
        if "€" in lower or "eur" in lower:
            val *= 10.8
        elif "$" in lower or "usd" in lower:
            val *= 10.0

        # Reject obviously wrong prices (under 50 MAD = parsing error)
        if val < 50:
            return None

        return round(val, 2)

    def _clean_price_display(self, s: str) -> str:
        if not s or s == "Voir prix" or s == "Prix non disponible":
            return s
        # Remove markdown strikethrough noise
        s = re.sub(r"~~.*?~~", "", s).strip()
        return s

    def _parse_user_price(self, s: Optional[str]) -> Optional[dict]:
        if not s:
            return None
        s = s.replace(",", ".").replace("\xa0", " ")
        # Range: "5000-8000 dh"
        m = re.search(r"(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)", s)
        if m:
            return {"min": float(m.group(1)), "max": float(m.group(2))}
        # "moins de X" / "max X"
        m = re.search(r"(?:moins de|max|under|ما يزيدش)\s*(\d+)", s, re.IGNORECASE)
        if m:
            return {"min": 0, "max": float(m.group(1))}
        # Single value → ±25% tolerance (wider than before)
        m = re.search(r"(\d+\.?\d*)", s)
        if m:
            val = float(m.group(1))
            return {"min": val * 0.75, "max": val * 1.25}
        return None
