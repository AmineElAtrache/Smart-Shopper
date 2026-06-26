"""Probe Sephora, Carrefour, Intersport for httpx vs Playwright suitability."""

from __future__ import annotations

import asyncio
import re
import sys

import httpx

SITES = {
    "sephora_ma": {
        "urls": [
            "https://www.sephora.ma/search?q=parfum",
            "https://www.sephora.ma/parfums/",
        ],
    },
    "nice_ma": {
        "urls": [
            "https://www.nice.ma/recherche?controller=search&s=parfum",
            "https://nice.ma/recherche?controller=search&s=parfum",
            "https://www.nice.ma/parfums",
        ],
    },
    "carrefour_ma": {
        "urls": [
            "https://www.carrefour.ma/recherche?q=lait",
            "https://carrefour.ma/",
        ],
    },
    "bringo_ma": {
        "urls": [
            "https://www.bringo.ma/fr_MA/search?q=lait",
            "https://www.bringo.ma/search?q=lait",
            "https://www.bringo.ma/fr_MA/",
        ],
    },
    "intersport_ma": {
        "urls": [
            "https://www.intersport.ma/search?q=chaussures",
            "https://intersport.ma/",
        ],
    },
    "planetsport_ma": {
        "urls": [
            "https://planetsport.ma/recherche?controller=search&s=chaussures",
            "https://planetsport.ma/search?q=chaussures",
            "https://planetsport.ma/",
        ],
    },
    "decathlon_ma": {
        "urls": [
            "https://www.decathlon.ma/search?query=chaussures",
        ],
    },
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "fr-MA,fr;q=0.9,en;q=0.8"}

PRICE_RE = re.compile(r"\d[\d\s.,]*\s*(?:MAD|DH|DHS|dh|dhs|mad|درهم)", re.I)
PRODUCT_JSON_RE = re.compile(r'"@type"\s*:\s*"Product"', re.I)
ITEMLIST_RE = re.compile(r'"@type"\s*:\s*"ItemList"', re.I)
SPA_SHELL_RE = re.compile(
    r'(<div id="(root|app|__next)"></div>|window\.__NUXT__|__NEXT_DATA__|data-reactroot)',
    re.I,
)
PRODUCT_LINK_RE = re.compile(
    r'<a[^>]+href=[^>]+(?:product|/p/|catalog|article|\.html)[^>]*>[^<]{5,}',
    re.I,
)


def analyze(name: str, url: str, html: str, status: int, final_url: str) -> dict:
    lower = html.lower()
    title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    return {
        "name": name,
        "url": url,
        "final_url": final_url,
        "status": status,
        "html_len": len(html),
        "has_price": bool(PRICE_RE.search(html)),
        "price_count": len(PRICE_RE.findall(html)),
        "has_product_jsonld": bool(PRODUCT_JSON_RE.search(html)),
        "has_itemlist_jsonld": bool(ITEMLIST_RE.search(html)),
        "spa_shell": bool(SPA_SHELL_RE.search(html)),
        "product_link_count": len(PRODUCT_LINK_RE.findall(html)),
        "title": title_match.group(1).strip()[:100] if title_match else None,
        "blocked": any(
            x in lower
            for x in [
                "captcha",
                "access denied",
                "cloudflare",
                "bot detection",
                "please enable javascript",
                "just a moment",
            ]
        ),
        "platform_hints": [
            h
            for h in [
                "shopify",
                "magento",
                "prestashop",
                "woocommerce",
                "demandware",
                "sfcc",
                "vtex",
                "hybris",
                "salesforce",
            ]
            if h in lower
        ],
    }


async def probe_url(client: httpx.AsyncClient, name: str, url: str) -> dict:
    try:
        response = await client.get(url)
        return analyze(name, url, response.text, response.status_code, str(response.url))
    except Exception as exc:  # noqa: BLE001
        return {"name": name, "url": url, "error": str(exc)}


async def probe_playwright(name: str, url: str, *, timeout: float = 25.0) -> dict:
    try:
        from agents.webscraping.tools.playwright_scraper import fetch_rendered_html

        html, final_url = await fetch_rendered_html(url, timeout=timeout, locale="fr-MA")
        return analyze(name, url, html, 200, final_url)
    except Exception as exc:  # noqa: BLE001
        return {"name": name, "url": url, "mode": "playwright", "error": str(exc)}


def verdict(httpx_result: dict) -> str:
    if httpx_result.get("error"):
        return "unknown (httpx error)"
    if httpx_result.get("blocked"):
        return "playwright (blocked/captcha on httpx)"
    if httpx_result.get("status", 0) >= 400:
        return "unknown (bad status)"
    has_products = (
        httpx_result.get("has_price")
        or httpx_result.get("has_product_jsonld")
        or httpx_result.get("has_itemlist_jsonld")
        or httpx_result.get("product_link_count", 0) >= 3
    )
    if has_products and not httpx_result.get("spa_shell"):
        return "httpx"
    if has_products and httpx_result.get("spa_shell"):
        return "httpx (partial — verify)"
    if httpx_result.get("spa_shell") and httpx_result.get("html_len", 0) < 80000:
        return "playwright (SPA shell, no products in raw HTML)"
    if httpx_result.get("html_len", 0) > 100000 and not has_products:
        return "playwright (large page but no parseable products)"
    return "playwright (no product signals in httpx HTML)"


async def main() -> int:
    best: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers=HEADERS) as client:
        for name, cfg in SITES.items():
            for url in cfg["urls"]:
                result = await probe_url(client, name, url)
                print("=== HTTX ===")
                for key, value in result.items():
                    print(f"{key}: {value}")
                score = (
                    int(result.get("has_price", False))
                    + int(result.get("has_product_jsonld", False))
                    + int(result.get("has_itemlist_jsonld", False))
                    + min(result.get("product_link_count", 0), 5)
                )
                prev = best.get(name)
                if prev is None or score > prev["_score"]:
                    result["_score"] = score
                    best[name] = result

    print("\n=== HTTX VERDICT (best URL per site) ===")
    for name, result in best.items():
        print(f"{name}: {verdict(result)}")
        print(f"  best_url: {result.get('url')}")
        print(f"  final_url: {result.get('final_url')}")
        print(f"  prices: {result.get('price_count')} | jsonld: {result.get('has_product_jsonld')} | links: {result.get('product_link_count')}")

    print("\n=== PLAYWRIGHT PROBE (best httpx URL per site) ===")
    for name, result in best.items():
        url = result.get("url")
        if not url:
            continue
        pw = await probe_playwright(name, url)
        print(f"--- {name} ---")
        for key, value in pw.items():
            print(f"{key}: {value}")
        httpx_has = (
            result.get("has_price")
            or result.get("has_product_jsonld")
            or result.get("product_link_count", 0) >= 3
        )
        pw_has = (
            pw.get("has_price")
            or pw.get("has_product_jsonld")
            or pw.get("product_link_count", 0) >= 3
        )
        if httpx_has and not pw.get("error"):
            print(f"RECOMMENDATION: httpx")
        elif pw_has and not httpx_has:
            print(f"RECOMMENDATION: playwright")
        elif httpx_has and pw_has:
            print(f"RECOMMENDATION: httpx first (playwright fallback)")
        else:
            print(f"RECOMMENDATION: needs manual review")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
