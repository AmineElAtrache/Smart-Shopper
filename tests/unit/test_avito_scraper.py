import pytest

from agents.webscraping.agent import MockScraperAgent, MockScraperConfig, scrape_products
from agents.webscraping.spiders.avito import build_search_url, parse_products
from shared.events.schemas import Channel, ProductQuery, ScrapeTaskAssigned


def _task() -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id="req_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="phone", brand="Samsung", budget=3000),
    )


def test_avito_build_search_url_uses_product_query() -> None:
    url = build_search_url(_task())

    assert url.startswith("https://www.avito.ma/fr/maroc/")
    assert "Samsung" in url
    assert "phone" in url


def test_avito_build_search_url_uses_city_and_color_entities() -> None:
    task = ScrapeTaskAssigned(
        request_id="req_002",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(
            product="phone",
            brand="Samsung",
            budget=3000,
            city="Casablanca",
            color="black",
        ),
    )

    url = build_search_url(task)

    assert url.startswith("https://www.avito.ma/fr/casablanca/")
    assert "Samsung" in url
    assert "telephone" in url
    assert "noir" in url
    assert "3000" not in url


def test_avito_parse_products_from_fixture() -> None:
    html = open("tests/fixtures/avito_search.html", encoding="utf-8").read()

    products = parse_products(html, _task(), page_url="https://www.avito.ma/fr/maroc/Samsung+phone")

    assert len(products) == 2
    assert {product.source for product in products} == {"avito"}
    assert {product.user_id for product in products} == {"telegram_123"}
    assert all(product.query == _task().query for product in products)
    assert products[0].title == "Samsung Galaxy A15 128GB"
    assert products[0].price == 2499
    assert str(products[0].url).startswith("https://www.avito.ma/")
    assert all(product.price <= 3750 for product in products)


def _patch_other_providers_empty(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    for provider in (
        "electrosalam",
        "mafiawaystore",
        "moteur",
        "mymarket",
        "ultrapc",
        "electroplanet",
        "jumia",
        "defacto",
        "biougnach",
        "marjane",
        "decathlon",
        "mubawab",
        "ikea",
        "palmarosa",
        "bringo",
        "planetsport",
    ):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)


@pytest.mark.asyncio
async def test_webscraping_agent_falls_back_when_avito_fails(monkeypatch) -> None:
    async def fail_scrape(task):
        raise RuntimeError("blocked")

    monkeypatch.setattr("agents.webscraping.agent.avito.scrape", fail_scrape)
    _patch_other_providers_empty(monkeypatch)

    products = await scrape_products(_task())

    assert len(products) == 0


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


@pytest.mark.asyncio
async def test_agent_publishes_avito_products(monkeypatch) -> None:
    async def fake_scrape(task):
        html = open("tests/fixtures/avito_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.avito.ma/fr/maroc/Samsung+phone")

    monkeypatch.setattr("agents.webscraping.agent.avito.scrape", fake_scrape)
    _patch_other_providers_empty(monkeypatch)
    producer = FakeProducer()
    agent = MockScraperAgent(config=MockScraperConfig(), producer=producer)

    products = await agent.handle_task(_task())

    assert len(products) == 2
    assert len(producer.published) == 2
    assert all(event.source == "avito" for _, event, _ in producer.published)
