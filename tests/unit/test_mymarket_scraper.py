import pytest

from agents.webscraping.agent import MockScraperAgent, MockScraperConfig, scrape_products
from agents.webscraping.spiders.mymarket import build_search_url, parse_products
from shared.events.schemas import Channel, ProductQuery, ScrapeTaskAssigned


def _task() -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id="req_mymarket_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="phone", brand="Samsung", budget=3000),
    )


def test_mymarket_build_search_url_uses_product_query() -> None:
    url = build_search_url(_task())

    assert url == "https://www.mymarket.ma/search?q=Samsung+phone"


def test_mymarket_parse_products_from_fixture() -> None:
    html = open("tests/fixtures/mymarket_search.html", encoding="utf-8").read()

    products = parse_products(html, _task(), page_url="https://www.mymarket.ma/catalogsearch/result/?q=Samsung+phone")

    assert len(products) == 2
    assert products[0].source == "mymarket"
    assert products[0].seller == "MyMarket"
    assert products[0].title == "Samsung Galaxy A15 128GB phone"
    assert products[0].price == 2499
    assert str(products[0].url) == "https://www.mymarket.ma/samsung-galaxy-a15-128gb.html"
    assert all(product.user_id == "telegram_123" for product in products)
    assert all(product.query == _task().query for product in products)


@pytest.mark.asyncio
async def test_webscraping_agent_includes_mymarket_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_mymarket_scrape(task):
        html = open("tests/fixtures/mymarket_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.mymarket.ma/catalogsearch/result/?q=Samsung+phone")

    for provider in (
        "avito",
        "electrosalam",
        "mafiawaystore",
        "moteur",
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
    monkeypatch.setattr("agents.webscraping.agent.mymarket.scrape", fake_mymarket_scrape)

    products = await scrape_products(_task())

    assert len(products) >= 2
    assert products[0].source == "mymarket"


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


@pytest.mark.asyncio
async def test_agent_publishes_mymarket_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_mymarket_scrape(task):
        html = open("tests/fixtures/mymarket_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.mymarket.ma/catalogsearch/result/?q=Samsung+phone")

    for provider in (
        "avito",
        "electrosalam",
        "mafiawaystore",
        "moteur",
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
    monkeypatch.setattr("agents.webscraping.agent.mymarket.scrape", fake_mymarket_scrape)
    producer = FakeProducer()
    agent = MockScraperAgent(config=MockScraperConfig(), producer=producer)

    products = await agent.handle_task(_task())

    assert len(products) >= 2
    assert len(producer.published) >= 2
    assert producer.published[0][1].source == "mymarket"
