"""Quick probe for beauty/grocery candidate sites."""

from __future__ import annotations

import asyncio
import re

import httpx

from agents.webscraping.tools.playwright_scraper import fetch_rendered_html

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "fr-MA,fr;q=0.9,en;q=0.8"}
MAD_RE = re.compile(r"\d[\d\s.,]*\s*(?:MAD|DH|DHS|dh|dhs|mad)", re.I)
NUM_PRICE_RE = re.compile(r'class="[^"]*price[^"]*"[^>]*>[^<]*\d', re.I)

CANDIDATES = [
    ("parfumeriemaroc", "https://parfumeriemaroc.com/?s=parfum&post_type=product"),
    ("palmarosa", "https://www.palmarosashop.com/collections/all?q=parfum"),
    ("palmarosa_search", "https://www.palmarosashop.com/search?q=sephora"),
    ("marjanemall_lait", "https://www.marjanemall.ma/catalogsearch/result?q=lait"),
    ("marjanemall_parfum", "https://www.marjanemall.ma/catalogsearch/result?q=parfum"),
    ("bringo_home", "https://www.bringo.ma/fr_MA/"),
    ("planetsport", "https://planetsport.ma/recherche?controller=search&s=chaussures"),
    ("decathlon_shoes", "https://www.decathlon.ma/4976-chaussures-et-baskets"),
]


def stats(html: str) -> dict:
    lower = html.lower()
    title = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    return {
        "mad_prices": len(MAD_RE.findall(html)),
        "price_classes": len(NUM_PRICE_RE.findall(html)),
        "product_tokens": lower.count("product"),
        "jsonld_product": '"@type":"product"' in lower or '"@type": "product"' in lower,
        "blocked": any(x in lower for x in ("cloudflare", "captcha", "just a moment", "enable javascript")),
        "title": title.group(1).strip()[:80] if title else None,
        "html_len": len(html),
    }


async def probe_httpx(url: str) -> dict:
    async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers=HEADERS) as client:
        response = await client.get(url)
        result = stats(response.text)
        result["status"] = response.status_code
        result["final_url"] = str(response.url)
        return result


async def probe_playwright(url: str) -> dict:
    html, final_url = await fetch_rendered_html(url, timeout=30, locale="fr-MA")
    result = stats(html)
    result["status"] = 200
    result["final_url"] = final_url
    return result


async def main() -> None:
    for name, url in CANDIDATES:
        print(f"\n===== {name} =====")
        print(f"url: {url}")
        try:
            hx = await probe_httpx(url)
            print("httpx:", hx)
        except Exception as exc:  # noqa: BLE001
            print("httpx ERROR:", exc)
            hx = None
        try:
            pw = await probe_playwright(url)
            print("playwright:", pw)
        except Exception as exc:  # noqa: BLE001
            print("playwright ERROR:", exc)
            pw = None

        if hx and pw:
            hx_ok = hx["mad_prices"] >= 3 or hx["price_classes"] >= 3
            pw_ok = pw["mad_prices"] >= 3 or pw["price_classes"] >= 3
            if hx_ok and not pw_ok:
                print("VERDICT: httpx")
            elif pw_ok and not hx_ok:
                print("VERDICT: playwright")
            elif hx_ok and pw_ok:
                print("VERDICT: httpx first (playwright fallback)")
            else:
                print("VERDICT: hard / blocked / needs API")


if __name__ == "__main__":
    asyncio.run(main())
