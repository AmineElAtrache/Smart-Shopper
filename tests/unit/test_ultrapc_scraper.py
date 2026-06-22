import pytest

from agents.webscraping.agent import MockScraperAgent, MockScraperConfig, scrape_products
from agents.webscraping.spiders.ultrapc import build_search_url, parse_products
from shared.events.schemas import Channel, ProductQuery, ScrapeTaskAssigned


def _task() -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id="req_ultrapc_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="omen", brand="HP", budget=6000),
    )


def test_ultrapc_build_search_url_uses_product_query() -> None:
    assert build_search_url(_task()) == "https://www.ultrapc.ma/recherche?controller=search&s=HP+omen"


def test_ultrapc_parse_products_from_fixture() -> None:
    html = open("tests/fixtures/ultrapc_search.html", encoding="utf-8").read()

    products = parse_products(html, _task(), page_url="https://www.ultrapc.ma/recherche?controller=search&s=HP+omen")

    assert len(products) == 1
    assert products[0].source == "ultrapc"
    assert products[0].seller == "UltraPC"
    assert products[0].title == "HP OMEN 16 Gaming Laptop"
    assert products[0].price == 6499
    assert str(products[0].url) == "https://www.ultrapc.ma/pc-portable/omen-16.html"
    assert products[0].availability == "in_stock"
    assert products[0].user_id == "telegram_123"
    assert products[0].query == _task().query


@pytest.mark.asyncio
async def test_webscraping_agent_includes_ultrapc_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_ultrapc_scrape(task):
        html = open("tests/fixtures/ultrapc_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.ultrapc.ma/recherche?controller=search&s=HP+omen")

    for provider in ("avito", "electrosalam", "mafiawaystore", "moteur", "mymarket", "electroplanet", "jumia", "defacto", "biougnach", "marjane", "decathlon", "mubawab", "ikea"):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.ultrapc.scrape", fake_ultrapc_scrape)

    products = await scrape_products(_task())

    assert len(products) == 1
    assert products[0].source == "ultrapc"


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


@pytest.mark.asyncio
async def test_agent_publishes_ultrapc_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_ultrapc_scrape(task):
        html = open("tests/fixtures/ultrapc_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.ultrapc.ma/recherche?controller=search&s=HP+omen")

    for provider in ("avito", "electrosalam", "mafiawaystore", "moteur", "mymarket", "electroplanet", "jumia", "defacto", "biougnach", "marjane", "decathlon", "mubawab", "ikea"):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.ultrapc.scrape", fake_ultrapc_scrape)
    producer = FakeProducer()
    agent = MockScraperAgent(config=MockScraperConfig(), producer=producer)

    products = await agent.handle_task(_task())

    assert len(products) == 1
    assert len(producer.published) == 1
    assert producer.published[0][1].source == "ultrapc"
