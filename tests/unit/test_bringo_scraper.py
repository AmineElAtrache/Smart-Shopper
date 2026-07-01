import pytest

from agents.webscraping.agent import MockScraperAgent, MockScraperConfig, scrape_products
from agents.webscraping.spiders.bringo import build_search_url, parse_products
from shared.events.schemas import Channel, ProductQuery, ScrapeTaskAssigned

OTHER_PROVIDERS = (
    "avito",
    "electrosalam",
    "mafiawaystore",
    "moteur",
    "mymarket",
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
    "planetsport",
)


def _task() -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id="req_bringo_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="milk", budget=100),
    )


def test_bringo_build_search_url_uses_constructor_api() -> None:
    url = build_search_url(_task())
    assert url.startswith("https://ac.cnstrc.com/v1/autocomplete/lait?key=")
    assert "num_results_Products=24" in url


def test_bringo_parse_products_from_fixture() -> None:
    payload = open("tests/fixtures/bringo_search.json", encoding="utf-8").read()
    products = parse_products(payload, _task(), page_url=build_search_url(_task()))

    assert len(products) == 2
    assert products[0].source == "bringo"
    assert products[0].seller == "Bringo Carrefour"
    assert "Lait" in products[0].title
    assert products[0].price == 58.95
    assert str(products[0].url) == "https://www.bringo.ma/fr_MA/products/vendor-2-553571"
    assert products[0].metadata["category"] == "grocery"
    assert products[0].query == _task().query


@pytest.mark.asyncio
async def test_webscraping_agent_includes_bringo_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_bringo_scrape(task):
        payload = open("tests/fixtures/bringo_search.json", encoding="utf-8").read()
        return parse_products(payload, task, page_url=build_search_url(task))

    for provider in OTHER_PROVIDERS:
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.bringo.scrape", fake_bringo_scrape)

    products = await scrape_products(_task())

    assert len(products) == 2
    assert all(product.source == "bringo" for product in products)


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


@pytest.mark.asyncio
async def test_agent_publishes_bringo_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_bringo_scrape(task):
        payload = open("tests/fixtures/bringo_search.json", encoding="utf-8").read()
        return parse_products(payload, task, page_url=build_search_url(task))

    for provider in OTHER_PROVIDERS:
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.bringo.scrape", fake_bringo_scrape)
    producer = FakeProducer()
    agent = MockScraperAgent(config=MockScraperConfig(), producer=producer)

    products = await agent.handle_task(_task())

    assert len(products) == 2
    assert len(producer.published) == 2
    assert producer.published[0][1].source == "bringo"
