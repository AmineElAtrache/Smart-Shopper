import pytest

from agents.webscraping.agent import MockScraperAgent, MockScraperConfig, scrape_products
from agents.webscraping.spiders.marjane import build_search_url, parse_products
from shared.events.schemas import Channel, ProductQuery, ScrapeTaskAssigned


def _task() -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id="req_marjane_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="lait", budget=100),
    )


def test_marjane_build_search_url_uses_product_query() -> None:
    assert build_search_url(_task()) == "https://www.marjanemall.ma/catalogsearch/result?q=lait"


def test_marjane_parse_products_from_fixture() -> None:
    html = open("tests/fixtures/marjane_search.html", encoding="utf-8").read()
    products = parse_products(html, _task(), page_url="https://www.marjanemall.ma/search?q=lait")

    assert len(products) == 2
    assert products[0].source == "marjane"
    assert products[0].seller == "Marjane"
    assert products[0].title == "Lait UHT Entier Jaouda 1L"
    assert products[0].price == 11.5
    assert str(products[0].url) == "https://www.marjanemall.ma/product/lait-uht-entier-jaouda-1l"
    assert products[0].availability == "in_stock"
    assert products[0].query == _task().query


@pytest.mark.asyncio
async def test_webscraping_agent_includes_marjane_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_marjane_scrape(task):
        html = open("tests/fixtures/marjane_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.marjanemall.ma/search?q=lait")

    for provider in ("avito", "electrosalam", "mafiawaystore", "moteur", "mymarket", "ultrapc", "electroplanet", "jumia", "defacto", "biougnach", "decathlon", "mubawab", "ikea", "palmarosa", "bringo", "planetsport"):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.marjane.scrape", fake_marjane_scrape)

    products = await scrape_products(_task())

    assert len(products) == 2
    assert products[0].source == "marjane"


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


@pytest.mark.asyncio
async def test_agent_publishes_marjane_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_marjane_scrape(task):
        html = open("tests/fixtures/marjane_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.marjanemall.ma/search?q=lait")

    for provider in ("avito", "electrosalam", "mafiawaystore", "moteur", "mymarket", "ultrapc", "electroplanet", "jumia", "defacto", "biougnach", "decathlon", "mubawab", "ikea", "palmarosa", "bringo", "planetsport"):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.marjane.scrape", fake_marjane_scrape)
    producer = FakeProducer()
    agent = MockScraperAgent(config=MockScraperConfig(), producer=producer)

    products = await agent.handle_task(_task())

    assert len(products) == 2
    assert len(producer.published) == 2
    assert producer.published[0][1].source == "marjane"
