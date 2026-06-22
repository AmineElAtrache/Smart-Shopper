import pytest

from agents.webscraping.agent import MockScraperAgent, MockScraperConfig, scrape_products
from agents.webscraping.spiders.decathlon import build_search_url, parse_products
from shared.events.schemas import Channel, ProductQuery, ScrapeTaskAssigned


def _task() -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id="req_decathlon_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="shoes", budget=600),
    )


def test_decathlon_build_search_url_uses_product_query() -> None:
    assert build_search_url(_task()) == "https://www.decathlon.ma/4976-chaussures-et-baskets"


def test_decathlon_parse_products_from_fixture() -> None:
    html = open("tests/fixtures/decathlon_search.html", encoding="utf-8").read()
    products = parse_products(html, _task(), page_url="https://www.decathlon.ma/search?query=chaussures")

    assert len(products) == 1
    assert products[0].source == "decathlon"
    assert products[0].seller == "Decathlon"
    assert products[0].title == "Chaussures running homme Run 100 noir"
    assert products[0].price == 349
    assert str(products[0].url) == "https://www.decathlon.ma/p/123456-789-chaussures-running-homme-run-100-noir.html"
    assert products[0].metadata["category"] == "sports"
    assert products[0].query == _task().query


@pytest.mark.asyncio
async def test_webscraping_agent_includes_decathlon_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_decathlon_scrape(task):
        html = open("tests/fixtures/decathlon_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.decathlon.ma/search?query=chaussures")

    for provider in ("avito", "electrosalam", "mafiawaystore", "moteur", "mymarket", "ultrapc", "electroplanet", "jumia", "defacto", "biougnach", "marjane", "mubawab", "ikea"):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.decathlon.scrape", fake_decathlon_scrape)

    products = await scrape_products(_task())

    assert len(products) == 1
    assert products[0].source == "decathlon"


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


@pytest.mark.asyncio
async def test_agent_publishes_decathlon_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_decathlon_scrape(task):
        html = open("tests/fixtures/decathlon_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.decathlon.ma/search?query=chaussures")

    for provider in ("avito", "electrosalam", "mafiawaystore", "moteur", "mymarket", "ultrapc", "electroplanet", "jumia", "defacto", "biougnach", "marjane", "mubawab", "ikea"):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.decathlon.scrape", fake_decathlon_scrape)
    producer = FakeProducer()
    agent = MockScraperAgent(config=MockScraperConfig(), producer=producer)

    products = await agent.handle_task(_task())

    assert len(products) == 1
    assert len(producer.published) == 1
    assert producer.published[0][1].source == "decathlon"
