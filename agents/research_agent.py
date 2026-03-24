import asyncio, logging, os, re
from scrapers.avito import scrape_avito
from scrapers.jumia import scrape_jumia

logger = logging.getLogger(__name__)
MAX   = int(os.getenv("MAX_RESULTS_PER_SOURCE", "6"))
DELAY = float(os.getenv("SCRAPE_DELAY", "1.5"))

SKIP_WORDS = {
    "bghit","bghi","wach","wasch","wash","nchri","nshri",
    "3tini","atini","fin","kayn","kayna","3ando","3endo",
    "3ndo","3andi","3endi","endi","fe","fi","f","mn","b","bi","l","dial",
    "kan9eleb","9eleb","3la","ndir","nchri","nshri",
    "بغيت","واش","فين","كاين","نشري","عطيني",
}


class ResearchAgent:

    async def run(self, entities: dict) -> dict:
        queries    = self._build_queries(entities)
        city       = entities.get("city")
        primary    = queries[0]
        price_range = self._price_range(entities.get("price"))

        logger.info(f"Research Agent using queries: {queries}")
        logger.info(f"Price range for Avito filter: {price_range}")

        jumia_r, avito_r = await asyncio.gather(
            scrape_jumia(primary, MAX, DELAY, price_range=price_range),
            scrape_avito(primary, city, MAX, DELAY * 1.2, price_range=price_range),
            return_exceptions=True,
        )

        if isinstance(jumia_r, Exception):
            logger.error(f"Jumia failed: {jumia_r}")
            jumia_r = []
        if isinstance(avito_r, Exception):
            logger.error(f"Avito failed: {avito_r}")
            avito_r = []

        total = len(jumia_r) + len(avito_r)
        logger.info(f"Research: Jumia={len(jumia_r)} Avito={len(avito_r)} total={total}")

        return {
            "queries_used": queries,
            "jumia":  jumia_r,
            "avito":  avito_r,
            "google": [],
            "ddg":    [],
            "total":  total,
        }

    def _price_range(self, price_str: str) -> dict | None:
        """
        Convert user's stated price into a min-max range for Avito URL filter.

        Examples:
          "4000 dh"       → min=3000, max=5000   (user said 4000 → ±25%)
          "4000-6000 dh"  → min=4000, max=6000   (exact range)
          "moins de 5000" → min=0,    max=5000
          "3000 درهم"     → min=2250, max=3750
        """
        if not price_str:
            return None

        s = price_str.replace(",", ".").replace("\xa0", " ")

        # Explicit range: "3000-5000 dh"
        m = re.search(r"(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)", s)
        if m:
            return {"min": int(float(m.group(1))), "max": int(float(m.group(2)))}

        # Upper limit: "moins de 5000" / "max 5000" / "ما يزيدش 5000"
        m = re.search(r"(?:moins de|max|under|ما يزيدش)\s*(\d+)", s, re.IGNORECASE)
        if m:
            return {"min": 0, "max": int(m.group(1))}

        # Single value → ±25% tolerance
        # "4000 dh" → min=3000, max=5000
        m = re.search(r"(\d+\.?\d*)", s)
        if m:
            val = float(m.group(1))
            return {
                "min": int(val * 0.75),
                "max": int(val * 1.25),
            }

        return None

    def _build_queries(self, entities: dict) -> list[str]:
        product = entities.get("product", "")
        brand   = entities.get("brand", "")
        color   = entities.get("color", "")
        phrase  = self._product_phrase(entities)

        queries = []

        parts = []
        if brand:  parts.append(brand)
        parts.append(phrase if phrase else product)
        if color:  parts.append(color)
        queries.append(" ".join(p for p in parts if p))

        if color and phrase:
            queries.append(f"{brand} {phrase}".strip() if brand else phrase)

        if product and product not in " ".join(queries):
            queries.append(product)

        seen, uniq = set(), []
        for q in queries:
            q = q.strip()
            if q and q not in seen:
                seen.add(q)
                uniq.append(q)

        return uniq[:3] if uniq else [entities.get("query", "produit")]

    def _product_phrase(self, entities: dict) -> str:
        query = entities.get("query", "").lower()
        city  = (entities.get("city") or "").lower()

        tokens = query.split()
        kept   = []
        for tok in tokens:
            clean = re.sub(r"[^\w]", "", tok)
            if not clean:
                continue
            if clean in SKIP_WORDS:
                continue
            if city and clean in city.split():
                continue
            if re.match(r"^\d+(?:dh|mad|درهم)?$", clean):
                continue
            kept.append(clean)

        return " ".join(kept).strip()