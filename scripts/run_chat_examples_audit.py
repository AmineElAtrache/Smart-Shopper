"""Audit the 13 chat-bot example queries against live NER + orchestrator query build."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass

from agents.decision.tools.scoring_engine import filter_relevant_products
from agents.orchestrator.tools.ner_client import GrpcNerClient, NerClient
from agents.orchestrator.tools.task_router import build_product_query
from models.ner.product_vocabulary import is_actionable_product_value
from shared.events.schemas import Availability, ProductQuery, RawProduct

EXAMPLES: list[dict] = [
    {
        "id": 1,
        "group": "Fixed — for/f junk",
        "text": "I want to buy a fridge for 8000 DH",
        "expect": {
            "product_in": {"fridge", "refrigerator"},
            "budget": 8000.0,
            "not_product": {"f"},
        },
    },
    {
        "id": 2,
        "group": "Fixed — for/f junk",
        "text": "kan9lebe 3la chi telaja fes tkone jdida we maghalyach",
        "expect": {
            "product_in": {"fridge", "refrigerator"},
            "city": "fes",
            "not_product": {"f"},
        },
    },
    {
        "id": 3,
        "group": "Fixed — for/f junk",
        "text": "bghit chi réfrigérateur f casa b 7000 dh",
        "expect": {
            "product_in": {"fridge", "refrigerator"},
            "city": "casablanca",
            "budget": 7000.0,
            "not_product": {"f"},
        },
    },
    {
        "id": 4,
        "group": "Darija — f preposition",
        "text": "bghit laptop f casablanca b 6000dh",
        "expect": {
            "product_in": {"laptop", "pc"},
            "city": "casablanca",
            "budget": 6000.0,
            "not_product": {"f"},
        },
    },
    {
        "id": 5,
        "group": "Darija — f preposition",
        "text": "bghit hp omen f fes b 6000dh",
        "expect": {
            "product_in": {"omen", "laptop", "pc"},
            "city": "fes",
            "brand": "HP",
            "budget": 6000.0,
            "not_product": {"f"},
        },
    },
    {
        "id": 6,
        "group": "Darija — f preposition",
        "text": "bghit Samsung phone black f Casablanca b 3000 dh",
        "expect": {
            "product": "phone",
            "brand": "Samsung",
            "city": "casablanca",
            "color": "black",
            "budget": 3000.0,
            "not_product": {"f"},
        },
    },
    {
        "id": 7,
        "group": "Normal",
        "text": "Bghit Samsung phone b 3000 dh",
        "expect": {
            "product": "phone",
            "brand": "Samsung",
            "budget": 3000.0,
        },
    },
    {
        "id": 8,
        "group": "Normal",
        "text": "bghit samsng phne black f casaa b 3000dh",
        "expect": {
            "product": "phone",
            "brand": "Samsung",
            "city": "casablanca",
            "color": "black",
            "budget": 3000.0,
        },
    },
    {
        "id": 9,
        "group": "Normal",
        "text": "kan9lebe 3la chi pc ykone nadi mayfotch 3000ddh",
        "expect": {
            "product_in": {"pc", "laptop"},
            "budget": 3000.0,
        },
    },
    {
        "id": 10,
        "group": "Normal",
        "text": "bghit tomobile golf kehla we ana 3endi hi 50000dh",
        "expect": {
            "product_in": {"golf", "car"},
            "brand": "Volkswagen",
            "color": "black",
            "budget": 50000.0,
        },
    },
    {
        "id": 11,
        "group": "Budget + product",
        "text": "I need a washing machine under 5000 DH",
        "expect": {
            "product_in": {"washing machine", "washing_machine", "machine"},
            "budget": 5000.0,
        },
    },
    {
        "id": 12,
        "group": "Budget + product",
        "text": "bghit télé f marrakech b 2500 dhs",
        "expect": {
            "product_in": {"tv", "television", "tele"},
            "city": "marrakech",
            "budget": 2500.0,
            "not_product": {"f", "phone"},
        },
    },
    {
        "id": 13,
        "group": "Budget + product",
        "text": "looking for air conditioner in rabat max 4000 dh",
        "expect": {
            "product_in": {"air conditioner", "air_conditioner", "ac", "climatiseur"},
            "city": "rabat",
            "budget": 4000.0,
            "not_product": {"air"},
        },
    },
]


@dataclass
class RowResult:
    example_id: int
    text: str
    ok: bool
    issues: list[str]
    entities: dict[str, str]
    query: dict[str, object]
    decision_junk_blocked: bool | None


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _check(expect: dict, entities: dict[str, str], query: ProductQuery) -> list[str]:
    issues: list[str] = []

    product = _norm(query.product)
    if "product" in expect and product != _norm(str(expect["product"])):
        issues.append(f"product expected {expect['product']!r}, got {query.product!r}")
    if "product_in" in expect and product not in {_norm(v) for v in expect["product_in"]}:
        issues.append(f"product expected one of {expect['product_in']}, got {query.product!r}")
    if "not_product" in expect and product in {_norm(v) for v in expect["not_product"]}:
        issues.append(f"product must not be junk {expect['not_product']}, got {query.product!r}")
    if not is_actionable_product_value(query.product) and product:
        issues.append(f"product {query.product!r} is not actionable (single-letter junk)")

    for field in ("brand", "city", "color"):
        if field not in expect:
            continue
        actual = _norm(getattr(query, field))
        expected = _norm(str(expect[field]))
        if actual != expected:
            issues.append(f"{field} expected {expect[field]!r}, got {getattr(query, field)!r}")

    if "budget" in expect:
        if query.budget is None:
            issues.append(f"budget expected {expect['budget']}, got None")
        elif abs(float(query.budget) - float(expect["budget"])) > 0.01:
            issues.append(f"budget expected {expect['budget']}, got {query.budget}")

    return issues


async def main() -> int:
    parser = argparse.ArgumentParser(description="Audit chat-bot example queries.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use live NER gRPC service (restart NER after code changes).",
    )
    args = parser.parse_args()

    client: NerClient | GrpcNerClient = (
        GrpcNerClient(host="localhost", port=50051, timeout=60.0)
        if args.live
        else NerClient()
    )
    if args.live:
        print("Mode: live NER gRPC (restart models.ner.grpc_server if code changed)\n")
    else:
        print("Mode: in-process NER (current codebase)\n")

    results: list[RowResult] = []

    junk_product = RawProduct(
        request_id="audit",
        source="palmarosa",
        title="CHERRY F HAIR FOOD",
        price=120,
        url="https://example.com/cherry-f",
        availability=Availability.IN_STOCK,
    )

    for example in EXAMPLES:
        text = example["text"]
        entities_list = await client.extract(text)
        entities = {entity.type: entity.value for entity in entities_list}
        query = build_product_query(entities_list)
        issues = _check(example["expect"], entities, query)

        junk_blocked: bool | None = None
        if example["id"] in {1, 2, 3, 4, 5, 6, 12}:
            kept = filter_relevant_products([junk_product], query)
            junk_blocked = len(kept) == 0

        results.append(
            RowResult(
                example_id=example["id"],
                text=text,
                ok=not issues and (junk_blocked is not False),
                issues=issues + ([] if junk_blocked is not False else ["Palmarosa junk was NOT blocked"]),
                entities=entities,
                query={
                    "product": query.product,
                    "brand": query.brand,
                    "budget": query.budget,
                    "city": query.city,
                    "color": query.color,
                    "quality": query.quality,
                },
                decision_junk_blocked=junk_blocked,
            )
        )

    passed = sum(1 for row in results if row.ok)
    print(f"\n=== Chat examples audit: {passed}/{len(results)} passed ===\n")
    for example, row in zip(EXAMPLES, results):
        status = "PASS" if row.ok else "FAIL"
        print(f"[{status}] #{row.example_id} ({example['group']})")
        print(f"  Q: {row.text}")
        print(f"  Query: {json.dumps(row.query, ensure_ascii=False)}")
        if row.decision_junk_blocked is not None:
            print(f"  Palmarosa junk blocked: {row.decision_junk_blocked}")
        if row.issues:
            for issue in row.issues:
                print(f"  ! {issue}")
        print()

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
