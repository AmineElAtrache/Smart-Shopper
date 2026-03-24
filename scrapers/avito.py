"""
scrapers/avito.py  (v4 — selectors from live HTML analysis)
Card selector : a.sc-1jge648-0
Title         : p.iHApav  OR  img[alt] (product image)
Price         : p.dJAfqm
Location      : p.layWaX (contains "dans")
URL           : href on the <a> card
"""
import asyncio, logging, re
from typing import Optional
import httpx
from bs4 import BeautifulSoup
from scrapers.jumia import ProductResult

logger   = logging.getLogger(__name__)
BASE_URL = "https://www.avito.ma"
HEADERS  = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "fr-MA,fr;q=0.9,ar;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
CITY_MAP = {
    "casablanca": "casablanca", "الدار البيضاء": "casablanca", "casa": "casablanca",
    "rabat": "rabat", "الرباط": "rabat",
    "marrakech": "marrakech", "مراكش": "marrakech",
    "fès": "fes-meknes", "fes": "fes-meknes", "فاس": "fes-meknes",
    "tanger": "tanger-tetouan-al-hoceima", "طنجة": "tanger-tetouan-al-hoceima",
    "agadir": "souss-massa", "أغادير": "souss-massa",
}


async def scrape_avito(query, city=None, max_results=5, delay=1.8, price_range=None):

    slug   = query.strip().lower().replace(" ", "+")
    region = CITY_MAP.get(city.lower()) if city else None
    base   = f"https://www.avito.ma/fr/{region or 'maroc'}/{slug}"
    url    = base + (f"?price={int(price_range['min'])}-{int(price_range['max'])}" if price_range else "")

    logger.info(f"Avito URL: {url}")
    await asyncio.sleep(delay)

    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as e:
        logger.error(f"Avito request failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")

    # Strategy 1: React class (changes often)
    cards = soup.select("a.sc-1jge648-0")

    # Strategy 2: any <a> linking to an Avito listing page
    if not cards:
        cards = [
            a for a in soup.find_all("a", href=True)
            if re.match(r"https://www\.avito\.ma/fr/\w.+_\d+\.htm", a.get("href", ""))
        ]
        logger.debug(f"Avito fallback href pattern: {len(cards)} cards")

    # Strategy 3: any <a> with href containing avito listing pattern
    if not cards:
        cards = [
            a for a in soup.find_all("a", href=True)
            if "/smartphone_et_t" in a.get("href", "") or
               "/mode-vetements" in a.get("href", "") or
               "/informatique" in a.get("href", "") or
               re.search(r"_\d{6,}\.htm", a.get("href", ""))
        ]
        logger.debug(f"Avito strategy 3: {len(cards)} cards")

    if not cards:
        logger.warning(f"Avito: 0 cards at {url} — dumping class names for debug")
        # Log all unique class names to help update selectors
        all_classes = set()
        for el in soup.find_all("a", class_=True):
            for c in el.get("class", []):
                all_classes.add(c)
        logger.debug(f"Avito <a> classes found: {sorted(all_classes)[:20]}")
        return []

    results = []
    seen    = set()

    for card in cards:
        try:
            # Title from p.iHApav or product image alt
            title = None
            title_el = card.select_one("p.iHApav")
            if title_el:
                title = title_el.get_text(strip=True)
            else:
                # Product image (not avatar) — src contains content.avito.ma
                for img in card.find_all("img", alt=True):
                    if img.get("src","").startswith("https://content.avito") or \
                       img.get("src","").startswith("https://images.avito"):
                        if len(img["alt"]) > 3:
                            title = img["alt"]
                            break

            if not title or len(title) < 3:
                continue

            key = title.lower()[:40]
            if key in seen:
                continue
            seen.add(key)

            # Price from p.dJAfqm or DH pattern
            price = "Prix non indiqué"
            price_el = card.select_one("p.dJAfqm")
            if price_el:
                price = price_el.get_text(strip=True)
            else:
                for p in card.find_all("p"):
                    t = p.get_text(strip=True)
                    if re.search(r"\d[\d\s]*DH", t, re.IGNORECASE):
                        price = t
                        break

            href     = card.get("href", "")
            full_url = href if href.startswith("http") else f"https://www.avito.ma{href}"

            img_el = next(
                (img for img in card.find_all("img")
                 if "content.avito" in img.get("src","") or
                    "images.avito" in img.get("src","")),
                None
            )
            image = img_el["src"] if img_el else None

            loc = None
            for p in card.find_all("p"):
                t = p.get_text(strip=True)
                if "dans" in t and len(t) < 80:
                    loc = t
                    break

            results.append(ProductResult(
                title=title, price=price,
                source="Avito.ma", url=full_url,
                image=image,
                extra={"location": loc},
            ))

            if len(results) >= max_results:
                break

        except Exception as e:
            logger.debug(f"Avito card error: {e}")

    logger.info(f"Avito: found {len(results)} results for '{query}'")
    return results