import pytest

from agents.webscraping.agent import MockScraperAgent, MockScraperConfig, scrape_products
from agents.webscraping.spiders.mafiawaystore import build_search_url, parse_products
from shared.events.schemas import Channel, ProductQuery, ScrapeTaskAssigned


def _task() -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id="req_mafia_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="chemise", budget=300),
    )


def test_mafiawaystore_build_search_url_uses_product_query() -> None:
    url = build_search_url(_task())

    assert url == "https://mafiawaystore.com/search?q=chemise"


def test_mafiawaystore_parse_products_from_fixture() -> None:
    html = open("tests/fixtures/mafiawaystore_search.html", encoding="utf-8").read()

    products = parse_products(html, _task(), page_url="https://mafiawaystore.com/search?q=chemise")

    assert len(products) == 1
    assert products[0].source == "mafiawaystore"
    assert products[0].seller == "Mafiaway Store"
    assert products[0].title == "Chemise en lin premium"
    assert products[0].price == 249
    assert str(products[0].url) == "https://mafiawaystore.com/products/chemise-en-lin-premium"
    assert products[0].metadata["category"] == "fashion"
    assert products[0].user_id == "telegram_123"
    assert products[0].query == _task().query


def _patch_other_providers_empty(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    for provider in (
        "avito",
        "electrosalam",
        "moteur",
        "mymarket",
        "ultrapc",
        "electroplanet",
        "jumia",
        "defacto",
    ):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)


@pytest.mark.asyncio
async def test_webscraping_agent_includes_mafiawaystore_products(monkeypatch) -> None:
    async def fake_mafiawaystore_scrape(task):
        html = open("tests/fixtures/mafiawaystore_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://mafiawaystore.com/search?q=chemise")

    _patch_other_providers_empty(monkeypatch)
    monkeypatch.setattr("agents.webscraping.agent.mafiawaystore.scrape", fake_mafiawaystore_scrape)

    products = await scrape_products(_task())

    assert len(products) == 1
    assert products[0].source == "mafiawaystore"


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


@pytest.mark.asyncio
async def test_agent_publishes_mafiawaystore_products(monkeypatch) -> None:
    async def fake_mafiawaystore_scrape(task):
        html = open("tests/fixtures/mafiawaystore_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://mafiawaystore.com/search?q=chemise")

    _patch_other_providers_empty(monkeypatch)
    monkeypatch.setattr("agents.webscraping.agent.mafiawaystore.scrape", fake_mafiawaystore_scrape)
    producer = FakeProducer()
    agent = MockScraperAgent(config=MockScraperConfig(), producer=producer)

    products = await agent.handle_task(_task())

    assert len(products) == 1
    assert len(producer.published) == 1
    assert producer.published[0][1].source == "mafiawaystore"
