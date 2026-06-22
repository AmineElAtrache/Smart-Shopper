import pytest

from agents.webscraping.agent import MockScraperAgent, MockScraperConfig, scrape_products
from agents.webscraping.spiders.biougnach import build_search_url, parse_products
from shared.events.schemas import Channel, ProductQuery, ScrapeTaskAssigned


def _task() -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id="req_biougnach_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="Smartphone", brand="Samsung", budget=3000),
    )


def test_biougnach_build_search_url_uses_product_query() -> None:
    assert build_search_url(_task()) == "https://www.biougnach.ma/shop/category/-50/4"


def test_biougnach_parse_products_from_fixture() -> None:
    html = open("tests/fixtures/biougnach_search.html", encoding="utf-8").read()
    products = parse_products(html, _task(), page_url="https://www.biougnach.ma/recherche?controller=search&s=Samsung+Smartphone")

    assert len(products) == 2
    assert products[0].source == "biougnach"
    assert products[0].seller == "Biougnach"
    assert products[0].title == "Samsung Galaxy A15 Smartphone"
    assert products[0].price == 2599
    assert str(products[0].url) == "https://www.biougnach.ma/smartphones/samsung-galaxy-a15.html"
    assert products[0].availability == "in_stock"
    assert products[0].query == _task().query


@pytest.mark.asyncio
async def test_webscraping_agent_includes_biougnach_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_biougnach_scrape(task):
        html = open("tests/fixtures/biougnach_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.biougnach.ma/recherche?controller=search&s=Samsung+Smartphone")

    for provider in ("avito", "electrosalam", "mafiawaystore", "moteur", "mymarket", "ultrapc", "electroplanet", "jumia", "defacto", "marjane", "decathlon", "mubawab", "ikea"):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.biougnach.scrape", fake_biougnach_scrape)

    products = await scrape_products(_task())

    assert len(products) == 2
    assert products[0].source == "biougnach"


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


@pytest.mark.asyncio
async def test_agent_publishes_biougnach_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_biougnach_scrape(task):
        html = open("tests/fixtures/biougnach_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.biougnach.ma/recherche?controller=search&s=Samsung+Smartphone")

    for provider in ("avito", "electrosalam", "mafiawaystore", "moteur", "mymarket", "ultrapc", "electroplanet", "jumia", "defacto", "marjane", "decathlon", "mubawab", "ikea"):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.biougnach.scrape", fake_biougnach_scrape)
    producer = FakeProducer()
    agent = MockScraperAgent(config=MockScraperConfig(), producer=producer)

    products = await agent.handle_task(_task())

    assert len(products) == 2
    assert len(producer.published) == 2
    assert producer.published[0][1].source == "biougnach"
