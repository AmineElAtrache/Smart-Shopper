import pytest

from agents.webscraping.agent import MockScraperAgent, MockScraperConfig, scrape_products
from agents.webscraping.spiders.ikea import build_search_url, parse_products
from shared.events.schemas import Channel, ProductQuery, ScrapeTaskAssigned


def _task() -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id="req_ikea_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="chair", budget=600),
    )


def test_ikea_build_search_url_uses_product_query() -> None:
    assert build_search_url(_task()) == "https://www.ikea.com/ma/fr/search/?q=chaise"


def test_ikea_parse_products_from_fixture() -> None:
    html = open("tests/fixtures/ikea_search.html", encoding="utf-8").read()
    products = parse_products(html, _task(), page_url="https://www.ikea.com/ma/fr/search/?q=chaise")

    assert len(products) == 2
    assert products[0].source == "ikea"
    assert products[0].seller == "IKEA"
    assert products[0].title == "ADDE Chaise blanc"
    assert products[0].price == 249
    assert str(products[0].url) == "https://www.ikea.com/ma/fr/p/adde-chaise-blanc-90214285/"
    assert products[0].metadata["category"] == "home"
    assert products[0].availability == "in_stock"
    assert products[0].query == _task().query


@pytest.mark.asyncio
async def test_webscraping_agent_includes_ikea_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_ikea_scrape(task):
        html = open("tests/fixtures/ikea_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.ikea.com/ma/fr/search/?q=chaise")

    for provider in ("avito", "electrosalam", "mafiawaystore", "moteur", "mymarket", "ultrapc", "electroplanet", "jumia", "defacto", "biougnach", "marjane", "decathlon", "mubawab", "palmarosa", "bringo", "planetsport"):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.ikea.scrape", fake_ikea_scrape)

    products = await scrape_products(_task())

    assert len(products) == 2
    assert products[0].source == "ikea"


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


@pytest.mark.asyncio
async def test_agent_publishes_ikea_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_ikea_scrape(task):
        html = open("tests/fixtures/ikea_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.ikea.com/ma/fr/search/?q=chaise")

    for provider in ("avito", "electrosalam", "mafiawaystore", "moteur", "mymarket", "ultrapc", "electroplanet", "jumia", "defacto", "biougnach", "marjane", "decathlon", "mubawab", "palmarosa", "bringo", "planetsport"):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.ikea.scrape", fake_ikea_scrape)
    producer = FakeProducer()
    agent = MockScraperAgent(config=MockScraperConfig(), producer=producer)

    products = await agent.handle_task(_task())

    assert len(products) == 2
    assert len(producer.published) == 2
    assert producer.published[0][1].source == "ikea"
