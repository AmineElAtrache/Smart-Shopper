"""Decision Agent: deduplicate, score, and rank raw scraped products."""

from __future__ import annotations

from agents.decision.tools.scoring_engine import rank_products
from shared.events.schemas import DecisionRanked, ProductQuery, RawProduct


class DecisionAgent:
    def rank(
        self,
        *,
        request_id: str,
        user_id: str,
        channel: str,
        query: ProductQuery,
        products: list[RawProduct],
        watch_id: str | None = None,
    ) -> DecisionRanked:
        return DecisionRanked(
            request_id=request_id,
            user_id=user_id,
            channel=channel,
            query=query,
            watch_id=watch_id,
            products=rank_products(products, query),
        )
