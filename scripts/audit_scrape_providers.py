"""Audit all marketplace scrapers: status, timing, blocks, and empty results.

Usage:
  python -m scripts.audit_scrape_providers
  python -m scripts.audit_scrape_providers "Bghit Samsung phone b 3000 dh"
  python -m scripts.audit_scrape_providers --parallel
  python -m scripts.audit_scrape_providers --smoke --parallel
  python -m scripts.audit_scrape_providers --json reports/audit.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from agents.webscraping.agent import SCRAPE_PROVIDERS
from shared.config import get_settings
from shared.events.schemas import Channel, ProductQuery, ScrapeTaskAssigned

STATUS_OK = "OK"
STATUS_EMPTY = "EMPTY"
STATUS_TIMEOUT = "TIMEOUT"
STATUS_BLOCKED = "BLOCKED"
STATUS_RATE_LIMIT = "RATE_LIMIT"
STATUS_ERROR = "ERROR"

# Realistic smoke query per provider (one phone query is wrong for beauty/grocery/sports/etc.)
PROVIDER_SMOKE_QUERIES: dict[str, ProductQuery] = {
    "jumia": ProductQuery(product="phone", brand="Samsung", budget=3000),
    "avito": ProductQuery(product="phone", brand="Samsung", budget=3000),
    "electrosalam": ProductQuery(product="laptop", brand="HP", budget=8000),
    "mafiawaystore": ProductQuery(product="shirt", budget=300),
    "moteur": ProductQuery(product="car", brand="Renault", budget=150000),
    "mymarket": ProductQuery(product="milk", budget=100),
    "ultrapc": ProductQuery(product="laptop", brand="HP", budget=10000),
    "electroplanet": ProductQuery(product="tv", budget=8000),
    "defacto": ProductQuery(product="shirt", budget=300),
    "biougnach": ProductQuery(product="tv", budget=5000),
    "marjane": ProductQuery(product="milk", budget=100),
    "decathlon": ProductQuery(product="shoes", budget=600),
    "mubawab": ProductQuery(product="apartment", city="Casablanca", budget=2000000),
    "ikea": ProductQuery(product="chair", budget=600),
    "palmarosa": ProductQuery(product="perfume", budget=500),
    "bringo": ProductQuery(product="milk", budget=100),
    "planetsport": ProductQuery(product="shoes", budget=900),
}


@dataclass
class ProviderAudit:
    name: str
    status: str
    duration_seconds: float
    product_count: int
    sample_url: str | None
    detail: str


def build_task(text: str, *, query: ProductQuery | None = None) -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id="provider_audit",
        user_id="audit",
        channel=Channel.TELEGRAM,
        user_text=text,
        query=query or ProductQuery(product="phone", brand="Samsung", budget=3000),
    )


def smoke_task(provider_name: str) -> ScrapeTaskAssigned:
    query = PROVIDER_SMOKE_QUERIES.get(
        provider_name,
        ProductQuery(product="phone", brand="Samsung", budget=3000),
    )
    parts = [query.brand, query.product, query.city]
    text = " ".join(str(part) for part in parts if part)
    return build_task(text or f"audit {provider_name}", query=query)


def classify_result(
    *,
    error: BaseException | None,
    product_count: int,
    duration_seconds: float,
    timeout_seconds: float,
) -> tuple[str, str]:
    if error is None:
        if product_count > 0:
            return STATUS_OK, f"{product_count} products"
        return STATUS_EMPTY, "No products parsed (page loaded but no matches)"

    message = str(error).strip()
    lowered = message.lower()

    if isinstance(error, TimeoutError) or "timeout" in lowered or "timed out" in lowered:
        if duration_seconds >= timeout_seconds * 0.95:
            return STATUS_TIMEOUT, message
        return STATUS_TIMEOUT, message

    if "403" in message or "forbidden" in lowered:
        return STATUS_BLOCKED, message
    if "401" in message or "unauthorized" in lowered:
        return STATUS_BLOCKED, message
    if "429" in message or "too many requests" in lowered:
        return STATUS_RATE_LIMIT, message
    if "target page, context or browser has been closed" in lowered:
        return STATUS_TIMEOUT, "Browser closed before page finished (often global timeout)"

    return STATUS_ERROR, message or error.__class__.__name__


async def audit_one_provider(
    name: str,
    provider: object,
    task: ScrapeTaskAssigned,
    *,
    timeout_seconds: float,
) -> ProviderAudit:
    started = time.perf_counter()
    error: BaseException | None = None
    products = []
    try:
        try:
            scrape_call = provider.scrape(task, timeout=timeout_seconds)  # type: ignore[attr-defined]
        except TypeError:
            scrape_call = provider.scrape(task)  # type: ignore[attr-defined]
        products = await asyncio.wait_for(scrape_call, timeout=timeout_seconds)
    except BaseException as exc:  # noqa: BLE001 - audit must capture all scraper failures
        error = exc
    duration = time.perf_counter() - started
    status, detail = classify_result(
        error=error,
        product_count=len(products),
        duration_seconds=duration,
        timeout_seconds=timeout_seconds,
    )
    sample_url = str(products[0].url) if products else None
    return ProviderAudit(
        name=name,
        status=status,
        duration_seconds=round(duration, 2),
        product_count=len(products),
        sample_url=sample_url,
        detail=_short_detail(detail),
    )


def _short_detail(detail: str, *, max_len: int = 90) -> str:
    cleaned = " ".join(detail.split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3] + "..."


async def audit_sequential_smoke(*, timeout_seconds: float) -> list[ProviderAudit]:
    results: list[ProviderAudit] = []
    for name, provider in SCRAPE_PROVIDERS:
        task = smoke_task(name)
        print(f"  -> {name} ({task.query.product}) ...", flush=True)
        results.append(
            await audit_one_provider(name, provider, task, timeout_seconds=timeout_seconds)
        )
    return results


async def audit_parallel_smoke(*, timeout_seconds: float) -> list[ProviderAudit]:
    print("  (each provider uses its own smoke query)", flush=True)

    async def run_one(name: str, provider: object) -> ProviderAudit:
        task = smoke_task(name)
        return await audit_one_provider(name, provider, task, timeout_seconds=timeout_seconds)

    pending = [run_one(name, provider) for name, provider in SCRAPE_PROVIDERS]
    return list(await asyncio.gather(*pending))


async def audit_sequential(task: ScrapeTaskAssigned, *, timeout_seconds: float) -> list[ProviderAudit]:
    results: list[ProviderAudit] = []
    for name, provider in SCRAPE_PROVIDERS:
        print(f"  -> {name} ...", flush=True)
        results.append(
            await audit_one_provider(name, provider, task, timeout_seconds=timeout_seconds)
        )
    return results


async def audit_parallel(task: ScrapeTaskAssigned, *, timeout_seconds: float) -> list[ProviderAudit]:
    print("  (all providers in parallel, like production)", flush=True)
    pending = [
        audit_one_provider(name, provider, task, timeout_seconds=timeout_seconds)
        for name, provider in SCRAPE_PROVIDERS
    ]
    return list(await asyncio.gather(*pending))


def print_report(
    results: list[ProviderAudit],
    *,
    query_text: str,
    timeout_seconds: float,
    mode: str,
) -> None:
    total_products = sum(item.product_count for item in results)
    width = 14
    print()
    print("=" * 88)
    print(f"SCRAPE PROVIDER AUDIT  |  query: {query_text}")
    print(f"timeout={timeout_seconds}s  mode={mode}  providers={len(results)}")
    print("=" * 88)
    print(f"{'SITE':<{width}} {'STATUS':<12} {'TIME(s)':>8} {'PRODUCTS':>9}  DETAIL")
    print("-" * 88)
    for item in sorted(results, key=lambda row: row.duration_seconds, reverse=True):
        print(
            f"{item.name:<{width}} {item.status:<12} {item.duration_seconds:>8.2f} "
            f"{item.product_count:>9}  {item.detail}"
        )
    print("-" * 88)

    counts: dict[str, int] = {}
    for item in results:
        counts[item.status] = counts.get(item.status, 0) + 1

    print(
        f"Summary: OK={counts.get(STATUS_OK, 0)}  EMPTY={counts.get(STATUS_EMPTY, 0)}  "
        f"TIMEOUT={counts.get(STATUS_TIMEOUT, 0)}  BLOCKED={counts.get(STATUS_BLOCKED, 0)}  "
        f"RATE_LIMIT={counts.get(STATUS_RATE_LIMIT, 0)}  ERROR={counts.get(STATUS_ERROR, 0)}  "
        f"total_products={total_products}"
    )
    print()
    print("Status guide:")
    print("  OK         - products returned")
    print("  EMPTY      - page fetched but parser found nothing")
    print("  TIMEOUT    - too slow or cancelled")
    print("  BLOCKED    - 403/401 anti-bot")
    print("  RATE_LIMIT - 429 too many requests")
    print("  ERROR      - other failure")
    print()
    ok_sites = [item.name for item in results if item.status == STATUS_OK]
    blocked = [item.name for item in results if item.status == STATUS_BLOCKED]
    slow = [item.name for item in results if item.status == STATUS_TIMEOUT]
    empty = [item.name for item in results if item.status == STATUS_EMPTY]
    if ok_sites:
        print(f"Working: {', '.join(ok_sites)}")
    if blocked:
        print(f"Blocked: {', '.join(blocked)}")
    if slow:
        print(f"Slow/timeout: {', '.join(slow)}")
    if empty:
        print(f"Empty (no products): {', '.join(empty)}")
    print("=" * 88)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit all scrape providers.")
    parser.add_argument(
        "query",
        nargs="*",
        help='Shopping query text (default: "Bghit Samsung phone b 3000 dh")',
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run all providers at once (production-like). Default is one-by-one for clear timing.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Use a realistic query per provider (recommended). Default uses one phone query for all.",
    )
    parser.add_argument(
        "--json",
        metavar="PATH",
        help="Save full report as JSON",
    )
    return parser.parse_args(argv)


async def async_main(argv: list[str]) -> int:
    args = parse_args(argv)
    settings = get_settings()
    query_text = " ".join(args.query).strip() or "Bghit Samsung phone b 3000 dh"
    task = build_task(query_text)
    timeout_seconds = settings.scrape_timeout_seconds
    mode = "parallel" if args.parallel else "sequential"
    if args.smoke:
        mode = f"{mode}+smoke"
        query_text = "per-provider smoke queries"

    print(f"Auditing {len(SCRAPE_PROVIDERS)} providers (explicit Playwright providers, httpx for the rest)")
    print(f"timeout={timeout_seconds}s mode={mode}")
    if args.smoke:
        print("Tip: --smoke uses perfume/milk/shoes/etc. per site instead of one phone query for all.")

    if args.smoke:
        if args.parallel:
            results = await audit_parallel_smoke(timeout_seconds=timeout_seconds)
        else:
            results = await audit_sequential_smoke(timeout_seconds=timeout_seconds)
    elif args.parallel:
        results = await audit_parallel(task, timeout_seconds=timeout_seconds)
    else:
        results = await audit_sequential(task, timeout_seconds=timeout_seconds)

    print_report(
        results,
        query_text=query_text,
        timeout_seconds=timeout_seconds,
        mode=mode,
    )

    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "query": query_text,
            "timeout_seconds": timeout_seconds,
            "mode": mode,
            "results": [asdict(item) for item in results],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Saved JSON report: {path.resolve()}")

    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main(sys.argv[1:])))


if __name__ == "__main__":
    main()
