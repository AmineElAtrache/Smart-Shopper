"""Add new scraper providers to existing unit-test skip lists."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests" / "unit"

OLD_TUPLE = '"ikea")'
NEW_TUPLE = '"ikea", "palmarosa", "bringo", "planetsport")'

OLD_LIST = '"ikea",\n    ):'
NEW_LIST = '"ikea",\n        "palmarosa",\n        "bringo",\n        "planetsport",\n    ):'


def main() -> None:
    updated = []
    for path in TESTS.glob("test_*_scraper.py"):
        if path.name in {
            "test_palmarosa_scraper.py",
            "test_bringo_scraper.py",
            "test_planetsport_scraper.py",
        }:
            continue
        text = path.read_text(encoding="utf-8")
        new_text = text.replace(OLD_TUPLE, NEW_TUPLE)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            updated.append(path.name)

    avito = TESTS / "test_avito_scraper.py"
    text = avito.read_text(encoding="utf-8")
    new_text = text.replace(
        '        "ikea",\n    ):',
        '        "ikea",\n        "palmarosa",\n        "bringo",\n        "planetsport",\n    ):',
    )
    if new_text != text:
        avito.write_text(new_text, encoding="utf-8")
        updated.append(avito.name)

    print("updated:", ", ".join(updated) or "none")


if __name__ == "__main__":
    main()
