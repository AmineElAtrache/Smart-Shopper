import pytest

from agents.webscraping.agent import MockScraperAgent, MockScraperConfig, scrape_products
from agents.webscraping.spiders.mubawab import build_search_url, parse_products
from shared.events.schemas import Channel, ProductQuery, ScrapeTaskAssigned


def _task() -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id="req_mubawab_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="apartment", city="casablanca", budget=1200000),
    )


def test_mubawab_build_search_url_uses_product_query() -> None:
    assert build_search_url(_task()) == "https://www.mubawab.ma/fr/st/casablanca/appartements-a-vendre"


def test_mubawab_parse_products_from_fixture() -> None:
    html = open("tests/fixtures/mubawab_search.html", encoding="utf-8").read()
    products = parse_products(html, _task(), page_url="https://www.mubawab.ma/fr/sc/casablanca/appartements-a-vendre")

    assert len(products) == 2
    assert products[0].source == "mubawab"
    assert products[0].seller == "Mubawab"
    assert products[0].title == "Appartement a vendre a Casablanca"
    assert products[0].price == 950000
    assert str(products[0].url) == "https://www.mubawab.ma/fr/a/123456/appartement-a-vendre-casablanca"
    assert products[0].metadata["category"] == "real_estate"
    assert products[0].query == _task().query


@pytest.mark.asyncio
async def test_webscraping_agent_includes_mubawab_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_mubawab_scrape(task):
        html = open("tests/fixtures/mubawab_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.mubawab.ma/fr/sc/casablanca/appartements-a-vendre")

    for provider in ("avito", "electrosalam", "mafiawaystore", "moteur", "mymarket", "ultrapc", "electroplanet", "jumia", "defacto", "biougnach", "marjane", "decathlon", "ikea"):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.mubawab.scrape", fake_mubawab_scrape)

    products = await scrape_products(_task())

    assert len(products) == 2
    assert products[0].source == "mubawab"


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


@pytest.mark.asyncio
async def test_agent_publishes_mubawab_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_mubawab_scrape(task):
        html = open("tests/fixtures/mubawab_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.mubawab.ma/fr/sc/casablanca/appartements-a-vendre")

    for provider in ("avito", "electrosalam", "mafiawaystore", "moteur", "mymarket", "ultrapc", "electroplanet", "jumia", "defacto", "biougnach", "marjane", "decathlon", "ikea"):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.mubawab.scrape", fake_mubawab_scrape)
    producer = FakeProducer()
    agent = MockScraperAgent(config=MockScraperConfig(), producer=producer)

    products = await agent.handle_task(_task())

    assert len(products) == 2
    assert len(producer.published) == 2
    assert producer.published[0][1].source == "mubawab"
