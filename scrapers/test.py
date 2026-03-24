import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "fr-MA,fr;q=0.9",
}

resp = httpx.get("https://www.jumia.ma/catalog/?q=iphone+17+pro+max&price=15000-19775#catalog-listing", headers=HEADERS, follow_redirects=True)
print("Status:", resp.status_code)
print("Final URL:", resp.url)

soup = BeautifulSoup(resp.text, "lxml")

# Save full HTML so we can inspect it
with open("jumia_debug.html", "w", encoding="utf-8") as f:
    f.write(resp.text)
print("Saved to jumia_debug.html")

# Try to find any card-like elements
for tag in ["article", "div", "li"]:
    elements = soup.find_all(tag, limit=3)
    for el in elements:
        classes = el.get("class", [])
        data = {k: v for k, v in el.attrs.items() if k.startswith("data-")}
        if classes or data:
            print(f"<{tag} class='{' '.join(classes)}' {data}>")