"""Integration hooks for Tier 1 global shared memory."""

from __future__ import annotations

from shared.events.schemas import DecisionRanked, PriceSnapshot, ProductQuery
from shared.memory.global_memory import GlobalMemory

PROVIDER_DOMAINS: dict[str, str] = {
    "jumia": "www.jumia.ma",
    "avito": "www.avito.ma",
    "electrosalam": "electrosalam.ma",
    "mafiawaystore": "mafiawaystore.com",
    "moteur": "www.moteur.ma",
    "mymarket": "www.mymarket.ma",
    "ultrapc": "www.ultrapc.ma",
    "electroplanet": "www.electroplanet.ma",
    "defacto": "www.defacto.com",
    "biougnach": "www.biougnach.ma",
    "marjane": "www.marjanemall.ma",
    "decathlon": "www.decathlon.ma",
    "mubawab": "www.mubawab.ma",
    "ikea": "www.ikea.com",
}


def provider_domain(provider_name: str) -> str:
    return PROVIDER_DOMAINS.get(provider_name.lower(), provider_name.lower())


def build_price_snapshots(ranked: DecisionRanked) -> list[PriceSnapshot]:
    if ranked.query is None or not ranked.products:
        return []
    snapshots: list[PriceSnapshot] = []
    for product in ranked.products[:3]:
        snapshots.append(
            PriceSnapshot(
                request_id=ranked.request_id,
                user_id=ranked.user_id,
                channel=ranked.channel,
                query=ranked.query,
                source=product.source,
                title=product.title,
                price=product.price,
                currency=product.currency,
                url=product.url,
            )
        )
    return snapshots


async def record_provider_health(
    memory: GlobalMemory,
    provider_name: str,
    *,
    product_count: int,
    elapsed_ms: float,
    error: str | None = None,
) -> None:
    domain = provider_domain(provider_name)
    if error == "timeout":
        status = "timeout"
    elif error:
        status = "error"
    elif product_count > 0:
        status = "healthy"
    else:
        status = "empty"

    await memory.set_site_health(
        domain,
        status,
        metadata={
            "provider": provider_name,
            "product_count": product_count,
            "elapsed_ms": round(elapsed_ms, 2),
            "error": error,
        },
    )


async def record_ranked_prices(memory: GlobalMemory, ranked: DecisionRanked) -> list[PriceSnapshot]:
    snapshots = build_price_snapshots(ranked)
    for snapshot in snapshots:
        await memory.record_price_snapshot(snapshot)
    return snapshots


async def record_query_price_samples(
    memory: GlobalMemory,
    *,
    request_id: str,
    user_id: str | None,
    channel,
    query: ProductQuery | None,
    products: list,
    limit: int = 5,
) -> None:
    """Record a small sample of raw scrape prices for trend tracking."""
    if query is None or not products:
        return
    for product in products[:limit]:
        await memory.record_price_snapshot(
            PriceSnapshot(
                request_id=request_id,
                user_id=user_id,
                channel=channel,
                query=query,
                source=product.source,
                title=product.title,
                price=product.price,
                currency=product.currency,
                url=product.url,
            )
        )
