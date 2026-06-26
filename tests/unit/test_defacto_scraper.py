import pytest

from agents.webscraping.agent import MockScraperAgent, MockScraperConfig, scrape_products
from agents.webscraping.spiders.defacto import build_search_url, parse_products
from shared.events.schemas import Channel, ProductQuery, ScrapeTaskAssigned


def _task() -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id="req_defacto_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="shirt", color="black", budget=300),
    )


def test_defacto_build_search_url_uses_product_query() -> None:
    assert build_search_url(_task()) == "https://www.defacto.com/fr-ma/search?q=chemise+noir"


def test_defacto_parse_products_from_fixture() -> None:
    html = open("tests/fixtures/defacto_search.html", encoding="utf-8").read()

    products = parse_products(html, _task(), page_url="https://www.defacto.com/en-m/search?q=shirt+black")

    assert len(products) == 1
    assert products[0].source == "defacto"
    assert products[0].seller == "DeFacto"
    assert products[0].title == "Regular Fit Black Shirt"
    assert products[0].price == 199
    assert str(products[0].url) == "https://www.defacto.com/en-m/regular-fit-black-shirt-123"
    assert products[0].metadata["category"] == "fashion"
    assert products[0].user_id == "telegram_123"
    assert products[0].query == _task().query


@pytest.mark.asyncio
async def test_webscraping_agent_includes_defacto_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_defacto_scrape(task):
        html = open("tests/fixtures/defacto_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.defacto.com/en-m/search?q=shirt+black")

    for provider in ("avito", "electrosalam", "mafiawaystore", "moteur", "mymarket", "ultrapc", "electroplanet", "jumia", "biougnach", "marjane", "decathlon", "mubawab", "ikea", "palmarosa", "bringo", "planetsport"):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.defacto.scrape", fake_defacto_scrape)

    products = await scrape_products(_task())

    assert len(products) == 1
    assert products[0].source == "defacto"


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


@pytest.mark.asyncio
async def test_agent_publishes_defacto_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_defacto_scrape(task):
        html = open("tests/fixtures/defacto_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.defacto.com/en-m/search?q=shirt+black")

    for provider in ("avito", "electrosalam", "mafiawaystore", "moteur", "mymarket", "ultrapc", "electroplanet", "jumia", "biougnach", "marjane", "decathlon", "mubawab", "ikea", "palmarosa", "bringo", "planetsport"):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.defacto.scrape", fake_defacto_scrape)
    producer = FakeProducer()
    agent = MockScraperAgent(config=MockScraperConfig(), producer=producer)

    products = await agent.handle_task(_task())

    assert len(products) == 1
    assert len(producer.published) == 1
    assert producer.published[0][1].source == "defacto"
