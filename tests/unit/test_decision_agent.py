from agents.decision.agent import DecisionAgent
from shared.events.schemas import Availability, ProductQuery, RawProduct


def test_decision_agent_ranks_best_product_first() -> None:
    query = ProductQuery(product="phone", brand="Samsung", budget=3000)
    products = [
        RawProduct(
            request_id="req_001",
            source="avito",
            title="Samsung Galaxy A15",
            price=3300,
            url="https://example.com/avito-a15",
            availability=Availability.UNKNOWN,
            seller="Private seller",
            rating=3.5,
        ),
        RawProduct(
            request_id="req_001",
            source="jumia",
            title="Samsung Galaxy A15 128GB",
            price=2499,
            url="https://example.com/jumia-a15",
            availability=Availability.IN_STOCK,
            seller="Jumia official",
            rating=4.5,
        ),
    ]

    ranked = DecisionAgent().rank(
        request_id="req_001",
        user_id="telegram_123",
        channel="telegram",
        query=query,
        products=products,
    )

    assert ranked.products[0].source == "jumia"
    assert ranked.products[0].score > ranked.products[1].score
    assert ranked.products[0].score_breakdown.price <= 40
    assert ranked.products[0].score_breakdown.trust <= 30


def test_decision_agent_filters_irrelevant_phone_results() -> None:
    query = ProductQuery(product="phone", budget=1390)
    products = [
        RawProduct(
            request_id="req_phone",
            source="jumia",
            title="MuscleTech Nitrotech 100% Whey Gold 2,28 kg",
            price=890,
            url="https://example.com/whey",
            availability=Availability.IN_STOCK,
            seller="Jumia official",
            rating=4.8,
        ),
        RawProduct(
            request_id="req_phone",
            source="ultrapc",
            title="SUPERLUX E205U USB MICROPHONE STUDIO USB",
            price=690,
            url="https://example.com/microphone",
            availability=Availability.IN_STOCK,
            rating=4.2,
        ),
        RawProduct(
            request_id="req_phone",
            source="jumia",
            title="Itel A100C 6,6 - 2+4 RAM + 64 ROM - Gold",
            price=879,
            url="https://example.com/itel-a100c",
            availability=Availability.IN_STOCK,
            seller="Jumia official",
            rating=4.1,
        ),
        RawProduct(
            request_id="req_phone",
            source="jumia",
            title="XIAOMI Redmi A5 3GB 64GB Sandy Gold",
            price=959,
            url="https://example.com/redmi-a5",
            availability=Availability.IN_STOCK,
            seller="Jumia official",
            rating=4.0,
        ),
    ]

    ranked = DecisionAgent().rank(
        request_id="req_phone",
        user_id="telegram_123",
        channel="telegram",
        query=query,
        products=products,
    )

    titles = [product.title.lower() for product in ranked.products]
    assert len(ranked.products) == 2
    assert all("whey" not in title for title in titles)
    assert all("microphone" not in title for title in titles)
    assert ranked.products[0].title.startswith("Itel") or ranked.products[0].title.startswith("XIAOMI")


def test_decision_agent_filters_laptop_accessories_and_noisy_pages() -> None:
    query = ProductQuery(product="laptop")
    products = [
        RawProduct(
            request_id="req_laptop",
            source="ultrapc",
            title="Razer Laptop Stand Support ergonomique pour ordinateur portable",
            price=649,
            url="https://example.com/laptop-stand",
            availability=Availability.IN_STOCK,
            rating=4.6,
        ),
        RawProduct(
            request_id="req_laptop",
            source="ultrapc",
            title="Chers clients, NOTRE MAGASIN EST OUVERT ULTRAPC continue a livrer les commandes Accueil Contact Plan du site",
            price=649,
            url="https://www.ultrapc.ma/",
            availability=Availability.IN_STOCK,
        ),
        RawProduct(
            request_id="req_laptop",
            source="avito",
            title="HP OMEN 15 laptop i7 GTX 1660",
            price=6200,
            url="https://example.com/hp-omen",
            availability=Availability.UNKNOWN,
            rating=3.8,
        ),
    ]

    ranked = DecisionAgent().rank(
        request_id="req_laptop",
        user_id="telegram_123",
        channel="telegram",
        query=query,
        products=products,
    )

    assert [product.title for product in ranked.products] == ["HP OMEN 15 laptop i7 GTX 1660"]


def test_decision_rejects_junk_single_letter_product_queries() -> None:
    query = ProductQuery(product="f", budget=8000.0)
    products = [
        RawProduct(
            request_id="req_f",
            source="palmarosa",
            title="CHERRY F HAIR FOOD",
            price=120,
            url="https://example.com/cherry-f",
            availability=Availability.IN_STOCK,
        ),
    ]

    ranked = DecisionAgent().rank(
        request_id="req_f",
        user_id="telegram_123",
        channel="telegram",
        query=query,
        products=products,
    )

    assert ranked.products == []


def test_decision_agent_diversifies_top_three_sources_when_possible() -> None:
    query = ProductQuery(product="phone", budget=3000)
    products = [
        RawProduct(
            request_id="req_diverse",
            source="jumia",
            title="Samsung Galaxy A15 phone",
            price=2499,
            url="https://example.com/jumia-a15",
            availability=Availability.IN_STOCK,
            seller="Jumia official",
            rating=4.5,
        ),
        RawProduct(
            request_id="req_diverse",
            source="jumia",
            title="Xiaomi Redmi A5 phone",
            price=959,
            url="https://example.com/jumia-redmi",
            availability=Availability.IN_STOCK,
            seller="Jumia official",
            rating=4.4,
        ),
        RawProduct(
            request_id="req_diverse",
            source="jumia",
            title="Itel A100C phone",
            price=879,
            url="https://example.com/jumia-itel",
            availability=Availability.IN_STOCK,
            seller="Jumia official",
            rating=4.3,
        ),
        RawProduct(
            request_id="req_diverse",
            source="avito",
            title="Samsung Galaxy A15 phone",
            price=2300,
            url="https://example.com/avito-a15",
            availability=Availability.UNKNOWN,
            seller="Private seller",
            rating=3.8,
        ),
    ]

    ranked = DecisionAgent().rank(
        request_id="req_diverse",
        user_id="telegram_123",
        channel="telegram",
        query=query,
        products=products,
    )

    assert len([product for product in ranked.products[:3] if product.source == "jumia"]) <= 2
    assert any(product.source == "avito" for product in ranked.products[:3])

def test_decision_agent_filters_air_fryer_false_positives() -> None:
    query = ProductQuery(product="air fryer", budget=2000)
    products = [
        RawProduct(
            request_id="req_airfryer",
            source="jumia",
            title="Taurus Air Fryer Digital Grill 12L",
            price=949,
            url="https://example.com/taurus-air-fryer",
            availability=Availability.IN_STOCK,
            seller="Jumia official",
            rating=4.5,
        ),
        RawProduct(
            request_id="req_airfryer",
            source="jumia",
            title="Taurus Climatiseur mobile AIR COOLERS R403 3 mode de fonctionnement",
            price=929,
            url="https://example.com/air-cooler",
            availability=Availability.IN_STOCK,
            seller="Jumia official",
            rating=4.4,
        ),
        RawProduct(
            request_id="req_airfryer",
            source="avito",
            title="MacBook Air fin disque SSD batterie 4h",
            price=800,
            url="https://example.com/macbook-air",
            availability=Availability.UNKNOWN,
        ),
    ]

    ranked = DecisionAgent().rank(
        request_id="req_airfryer",
        user_id="telegram_123",
        channel="telegram",
        query=query,
        products=products,
    )

    assert [product.title for product in ranked.products] == ["Taurus Air Fryer Digital Grill 12L"]

def test_decision_agent_filters_air_fryer_when_query_uses_underscore() -> None:
    query = ProductQuery(product="air_fryer", budget=2000)
    products = [
        RawProduct(
            request_id="req_airfryer_underscore",
            source="jumia",
            title="Friteuse sans huile Air Fryer 6L",
            price=799,
            url="https://example.com/friteuse-sans-huile",
            availability=Availability.IN_STOCK,
        ),
        RawProduct(
            request_id="req_airfryer_underscore",
            source="avito",
            title="MacBook Air 2017",
            price=1800,
            url="https://example.com/macbook-air",
            availability=Availability.UNKNOWN,
        ),
    ]

    ranked = DecisionAgent().rank(
        request_id="req_airfryer_underscore",
        user_id="telegram_123",
        channel="telegram",
        query=query,
        products=products,
    )

    assert [product.title for product in ranked.products] == ["Friteuse sans huile Air Fryer 6L"]


def test_decision_agent_rejects_phone_accessories_and_smarttag() -> None:
    query = ProductQuery(product="phone", color="blanc", budget=3000)
    products = [
        RawProduct(
            request_id="req_smarttag",
            source="electroplanet",
            title="SAMSUNG GALAXY SMARTTAG2 WHITE",
            price=249,
            url="https://www.electroplanet.ma/galaxy-smarttag2-white-samsung.html",
            availability=Availability.IN_STOCK,
            rating=4.0,
        ),
        RawProduct(
            request_id="req_smarttag",
            source="jumia",
            title="Samsung Galaxy Buds2 Pro White",
            price=899,
            url="https://example.com/galaxy-buds",
            availability=Availability.IN_STOCK,
            seller="Jumia official",
            rating=4.5,
        ),
        RawProduct(
            request_id="req_smarttag",
            source="avito",
            title="Samsung Galaxy A15 128GB Blanc",
            price=2800,
            url="https://example.com/galaxy-a15",
            availability=Availability.UNKNOWN,
            seller="Private seller",
            rating=3.8,
        ),
        RawProduct(
            request_id="req_smarttag",
            source="jumia",
            title="Coque Samsung Galaxy A15 transparente",
            price=49,
            url="https://example.com/coque-a15",
            availability=Availability.IN_STOCK,
            seller="Jumia official",
            rating=4.2,
        ),
    ]

    ranked = DecisionAgent().rank(
        request_id="req_smarttag",
        user_id="telegram_123",
        channel="telegram",
        query=query,
        products=products,
    )

    titles = [product.title.lower() for product in ranked.products]
    assert len(ranked.products) == 1
    assert "galaxy a15" in titles[0]
    assert all("smarttag" not in title for title in titles)
    assert all("buds" not in title for title in titles)
    assert all("coque" not in title for title in titles)


def test_decision_agent_keeps_budget_phone_without_primary_word_in_title() -> None:
    query = ProductQuery(product="phone", budget=3000)
    products = [
        RawProduct(
            request_id="req_model",
            source="jumia",
            title="Itel A100C 6,6 - 2+4 RAM + 64 ROM - Gold",
            price=879,
            url="https://example.com/itel-a100c",
            availability=Availability.IN_STOCK,
            seller="Jumia official",
            rating=4.1,
        ),
        RawProduct(
            request_id="req_model",
            source="jumia",
            title="XIAOMI Redmi A5 3GB 64GB Sandy Gold",
            price=959,
            url="https://example.com/redmi-a5",
            availability=Availability.IN_STOCK,
            seller="Jumia official",
            rating=4.0,
        ),
    ]

    ranked = DecisionAgent().rank(
        request_id="req_model",
        user_id="telegram_123",
        channel="telegram",
        query=query,
        products=products,
    )

    assert len(ranked.products) == 2
