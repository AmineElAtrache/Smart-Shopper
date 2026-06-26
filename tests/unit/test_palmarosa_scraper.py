import pytest

from agents.webscraping.agent import MockScraperAgent, MockScraperConfig, scrape_products
from agents.webscraping.spiders.palmarosa import build_search_url, parse_products
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
    "bringo",
    "planetsport",
)


def _task() -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id="req_palmarosa_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="perfume", budget=300),
    )


def test_palmarosa_build_search_url_uses_product_query() -> None:
    assert build_search_url(_task()) == "https://www.palmarosashop.com/search?q=parfum"


def test_palmarosa_parse_products_from_fixture() -> None:
    html = open("tests/fixtures/palmarosa_search.html", encoding="utf-8").read()
    products = parse_products(
        html,
        _task(),
        page_url="https://www.palmarosashop.com/search?q=parfum",
    )

    assert len(products) == 1
    assert products[0].source == "palmarosa"
    assert products[0].seller == "Palmarosa Shop"
    assert products[0].title == "BAIJA - TERRA CINNA EAU DE PARFUM 15ML"
    assert products[0].price == 170
    assert str(products[0].url) == "https://www.palmarosashop.com/baija-terra-cinna-eau-de-parfum-15ml"
    assert products[0].metadata["category"] == "beauty"
    assert products[0].query == _task().query


@pytest.mark.asyncio
async def test_webscraping_agent_includes_palmarosa_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_palmarosa_scrape(task):
        html = open("tests/fixtures/palmarosa_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.palmarosashop.com/search?q=parfum")

    for provider in OTHER_PROVIDERS:
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.palmarosa.scrape", fake_palmarosa_scrape)

    products = await scrape_products(_task())

    assert len(products) == 1
    assert products[0].source == "palmarosa"


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


@pytest.mark.asyncio
async def test_agent_publishes_palmarosa_products(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    async def fake_palmarosa_scrape(task):
        html = open("tests/fixtures/palmarosa_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.palmarosashop.com/search?q=parfum")

    for provider in OTHER_PROVIDERS:
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)
    monkeypatch.setattr("agents.webscraping.agent.palmarosa.scrape", fake_palmarosa_scrape)
    producer = FakeProducer()
    agent = MockScraperAgent(config=MockScraperConfig(), producer=producer)

    products = await agent.handle_task(_task())

    assert len(products) == 1
    assert len(producer.published) == 1
    assert producer.published[0][1].source == "palmarosa"
