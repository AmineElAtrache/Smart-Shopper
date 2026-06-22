import pytest

from agents.webscraping.agent import MockScraperAgent, MockScraperConfig, scrape_products
from agents.webscraping.spiders.electrosalam import build_search_url, parse_products
from shared.events.schemas import Channel, ProductQuery, ScrapeTaskAssigned


def _task() -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id="req_electro_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="omen", brand="HP", budget=6000),
    )


def test_electrosalam_build_search_url_uses_product_query() -> None:
    url = build_search_url(_task())

    assert url == "https://electrosalam.ma/search?q=HP+omen"


def test_electrosalam_parse_products_from_fixture() -> None:
    html = open("tests/fixtures/electrosalam_search.html", encoding="utf-8").read()

    products = parse_products(html, _task(), page_url="https://electrosalam.ma/search?q=HP+omen")

    assert len(products) == 1
    assert products[0].source == "electrosalam"
    assert products[0].seller == "ElectroSalam"
    assert products[0].title == "HP OMEN 16 Gaming Laptop"
    assert products[0].price == 6499
    assert str(products[0].url) == "https://electrosalam.ma/products/hp-omen-16-gaming-laptop"
    assert products[0].user_id == "telegram_123"
    assert products[0].query == _task().query


def _patch_other_providers_empty(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    for provider in (
        "avito",
        "mafiawaystore",
        "moteur",
        "mymarket",
        "ultrapc",
        "electroplanet",
        "jumia",
        "defacto",
    ):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)


@pytest.mark.asyncio
async def test_webscraping_agent_includes_electrosalam_products(monkeypatch) -> None:
    async def fake_electrosalam_scrape(task):
        html = open("tests/fixtures/electrosalam_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://electrosalam.ma/search?q=HP+omen")

    _patch_other_providers_empty(monkeypatch)
    monkeypatch.setattr("agents.webscraping.agent.electrosalam.scrape", fake_electrosalam_scrape)

    products = await scrape_products(_task())

    assert len(products) == 1
    assert products[0].source == "electrosalam"


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


@pytest.mark.asyncio
async def test_agent_publishes_electrosalam_products(monkeypatch) -> None:
    async def fake_electrosalam_scrape(task):
        html = open("tests/fixtures/electrosalam_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://electrosalam.ma/search?q=HP+omen")

    _patch_other_providers_empty(monkeypatch)
    monkeypatch.setattr("agents.webscraping.agent.electrosalam.scrape", fake_electrosalam_scrape)
    producer = FakeProducer()
    agent = MockScraperAgent(config=MockScraperConfig(), producer=producer)

    products = await agent.handle_task(_task())

    assert len(products) == 1
    assert len(producer.published) == 1
    assert producer.published[0][1].source == "electrosalam"
