"""
scrapers/jumia.py
Selectors confirmed from live HTML:
  card    : article.prd
  title   : h3.name
  price   : div.prc
  old     : div.old
  discount: div.bdg._dsct
  link    : a.core  (href)
  image   : img.img (data-src)
"""
import asyncio, logging
from dataclasses import dataclass, field
from typing import Optional
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE = "https://www.jumia.ma"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-MA,fr;q=0.9,ar;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.jumia.ma/",
}


@dataclass
class ProductResult:
    title:  str
    price:  str
    source: str
    url:    str
    image:  Optional[str] = None
    rating: Optional[str] = None
    extra:  dict = field(default_factory=dict)


async def scrape_jumia(
    query: str,
    max_results: int = 6,
    delay: float = 1.5,
    price_range: Optional[dict] = None,
) -> list[ProductResult]:

    encoded = query.replace(" ", "+")
    url     = f"{BASE}/catalog/?q={encoded}&sortBy=popularity"

    # Add price filter if provided — same format as Jumia URL
    # Example: ?price=15000-19775#catalog-listing
    if price_range:
        lo = int(price_range.get("min", 0))
        hi = int(price_range.get("max", 999999))
        url += f"&price={lo}-{hi}#catalog-listing"

    logger.info(f"Jumia URL: {url}")
    await asyncio.sleep(delay)

    try:
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=20, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as e:
        logger.error(f"Jumia request failed: {e}")
        return []

    soup  = BeautifulSoup(resp.text, "lxml")
    cards = soup.select("article.prd")

    if not cards:
        logger.warning(f"Jumia: no product cards found for '{query}'")
        return []

    results = []
    for card in cards[:max_results]:
        try:
            # Title — confirmed: h3.name
            title_el = card.select_one("h3.name")
            title    = title_el.get_text(strip=True) if title_el else None
            if not title:
                continue

            # Current price — confirmed: div.prc
            price_el  = card.select_one("div.prc")
            price_raw = price_el.get_text(strip=True) if price_el else None

            # Old price — confirmed: div.old
            old_el    = card.select_one("div.old")
            old_price = old_el.get_text(strip=True) if old_el else None

            # Discount badge — confirmed: div.bdg._dsct
            disc_el  = card.select_one("div.bdg._dsct")
            discount = disc_el.get_text(strip=True) if disc_el else None

            # URL — confirmed: a.core href
            link_el  = card.select_one("a.core")
            href     = link_el.get("href", "") if link_el else ""
            full_url = f"{BASE}{href}" if href.startswith("/") else href

            # Image — confirmed: img.img data-src
            img_el = card.select_one("img.img")
            image  = img_el.get("data-src") or img_el.get("src") if img_el else None

            # Build display price
            display_price = price_raw or "Prix non disponible"
            if old_price and discount:
                display_price = f"{price_raw}  (was {old_price}  {discount} off)"
            elif old_price:
                display_price = f"{price_raw}  (was {old_price})"

            results.append(ProductResult(
                title  = title,
                price  = display_price,
                source = "Jumia.ma",
                url    = full_url,
                image  = image,
                extra  = {"discount": discount, "old_price": old_price},
            ))

        except Exception as e:
            logger.debug(f"Jumia card parse error: {e}")

    logger.info(f"Jumia: found {len(results)} results for '{query}'")
    return results