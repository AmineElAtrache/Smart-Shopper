"""Analyze fixture HTML for parser design."""

from __future__ import annotations

import re
from pathlib import Path

FIXTURES = Path("tests/fixtures")


def analyze(name: str) -> None:
    path = FIXTURES / f"{name}_search.html"
    html = path.read_text(encoding="utf-8")
    print(f"\n=== {name} ({len(html)} bytes) ===")
    print("MAD:", len(re.findall(r"MAD", html, re.I)))
    print("DH:", len(re.findall(r"\bDH\b", html, re.I)))
    print("product hrefs:", len(re.findall(r'href="[^"]*(?:product|/p/|\.html)[^"]*"', html, re.I)))
    if "cdcDatalayer" in html:
        m = re.search(r"cdcDatalayer = (\{.*?\});", html)
        if m:
            print("cdcDatalayer items:", html[m.start() : m.start() + 200])
    if "__NEXT_DATA__" in html:
        print("has __NEXT_DATA__")
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
        if m:
            print("next data len:", len(m.group(1)))
    for pat in [r'"price"\s*:\s*"?(\d+)"?', r'class="price[^"]*"[^>]*>([^<]{1,40})']:
        hits = re.findall(pat, html[:200000])
        if hits:
            print("price sample:", hits[:3])
    urls = re.findall(r"https://www\.palmarosashop\.com/[a-z0-9-]+", html)
    if urls:
        print("palmarosa urls:", urls[:5])
    mad_prices = re.findall(r"(\d{1,4}(?:[,\.]\d{2})?)\s*MAD", html)
    if mad_prices:
        print("mad prices:", mad_prices[:5])
    rel_urls = re.findall(r'href="(/[a-z0-9][a-z0-9-]{4,80})"', html)
    if rel_urls:
        productish = [u for u in rel_urls if not u.startswith(("/_", "/icons", "/media", "/cart", "/login"))]
        print("relative urls:", productish[:8])


if __name__ == "__main__":
    for site in ("planetsport", "palmarosa", "bringo"):
        analyze(site)
