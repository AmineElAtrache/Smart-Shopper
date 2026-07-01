import re
from pathlib import Path

html = Path("tests/fixtures/palmarosa_search.html").read_text(encoding="utf-8")
idx = html.find("baija-terra-cinna-eau-de-parfum-15ml")
print(html[idx : idx + 800])
