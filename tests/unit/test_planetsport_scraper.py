import pytest

from agents.webscraping.agent import MockScraperAgent, MockScraperConfig, scrape_products
from agents.webscraping.spiders.planetsport import build_search_url, parse_products
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
    "bringo",
)


def _task() -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id="req_planetsport_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="shoes", budget=900),
    )


def test_planetsport_build_search_url_uses_product_query() -> None:
    assert (
        build_search_url(_task())
        == "https://planetsport.ma/recherche?controller=search&s=chaussures"
    )


def test_planetsport_parse_products_from_fixture() -> None:
    html = open("tests/fixtures/planetsport_search.html", encoding="utf-8").read()
    products = parse_products(
        html,
        _task(),
        page_url="https://planetsport.ma/recherche?controller=search&s=chaussures",
    )

    assert len(products) >= 1
    assert products[0].source == "planetsport"
    assert products[0].seller == "Planet Sport"
    assert "SAMBA" in products[0].title
    assert products[0].price == 786
    assert "planetsport.ma/chaussures/59786-samba-og-w-org.html" in str(products[0].url)
    assert products[0].metadata["category"] == "sports"
    assert products[0].query == _task().query


@pytest.mark.asyncio
async def test_webscraping_agent_includes_planetsport_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_planetsport_scrape(task):
        html = open("tests/fixtures/planetsport_search.html", encoding="utf-8").read()
        return parse_products(
            html,
            task,
            page_url="https://planetsport.ma/recherche?controller=search&s=chaussures",
        )

    for provider in OTHER_PROVIDERS:
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.planetsport.scrape", fake_planetsport_scrape)

    products = await scrape_products(_task())

    assert len(products) >= 1
    assert any(product.source == "planetsport" for product in products)


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


@pytest.mark.asyncio
async def test_agent_publishes_planetsport_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_planetsport_scrape(task):
        html = open("tests/fixtures/planetsport_search.html", encoding="utf-8").read()
        return parse_products(
            html,
            task,
            page_url="https://planetsport.ma/recherche?controller=search&s=chaussures",
        )

    for provider in OTHER_PROVIDERS:
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.planetsport.scrape", fake_planetsport_scrape)
    producer = FakeProducer()
    agent = MockScraperAgent(config=MockScraperConfig(), producer=producer)

    products = await agent.handle_task(_task())

    assert len(products) >= 1
    assert len(producer.published) >= 1
    assert producer.published[0][1].source == "planetsport"
