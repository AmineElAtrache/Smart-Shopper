import pytest

from agents.webscraping.agent import MockScraperAgent, MockScraperConfig, scrape_products
from agents.webscraping.spiders.moteur import build_search_url, parse_products
from shared.events.schemas import Channel, ProductQuery, ScrapeTaskAssigned


def _task() -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id="req_moteur_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=ProductQuery(product="x3", brand="BMW", budget=220000, city="casablanca"),
    )


def test_moteur_build_search_url_uses_budget_filter() -> None:
    url = build_search_url(_task())

    assert url == "https://www.moteur.ma/fr/voiture/achat-voiture-occasion/recherche/?prix_max=275000"


def test_moteur_parse_products_from_fixture() -> None:
    html = open("tests/fixtures/moteur_search.html", encoding="utf-8").read()

    products = parse_products(html, _task(), page_url="https://www.moteur.ma/fr/voiture/achat-voiture-occasion/")

    assert len(products) == 1
    assert products[0].source == "moteur"
    assert products[0].seller == "Moteur.ma"
    assert products[0].title == "BMW X3"
    assert products[0].price == 210000
    assert products[0].metadata["category"] == "vehicle"
    assert products[0].metadata["city"] == "Casablanca"
    assert products[0].metadata["year"] == "2016"
    assert products[0].metadata["transmission"] == "Automatique"
    assert products[0].metadata["fuel"] == "Diesel"
    assert products[0].metadata["mileage"] == "191,000 km"
    assert products[0].user_id == "telegram_123"
    assert products[0].query == _task().query


def _patch_other_providers_empty(monkeypatch) -> None:
    async def fake_empty(task):
        return []

    for provider in (
        "avito",
        "electrosalam",
        "mafiawaystore",
        "mymarket",
        "ultrapc",
        "electroplanet",
        "jumia",
        "defacto",
    ):
        monkeypatch.setattr(f"agents.webscraping.agent.{provider}.scrape", fake_empty)


@pytest.mark.asyncio
async def test_webscraping_agent_includes_moteur_products(monkeypatch) -> None:
    async def fake_moteur_scrape(task):
        html = open("tests/fixtures/moteur_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.moteur.ma/fr/voiture/achat-voiture-occasion/")

    _patch_other_providers_empty(monkeypatch)
    monkeypatch.setattr("agents.webscraping.agent.moteur.scrape", fake_moteur_scrape)

    products = await scrape_products(_task())

    assert len(products) == 1
    assert products[0].source == "moteur"


class FakeProducer:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, event, key=None) -> None:
        self.published.append((topic, event, key))


@pytest.mark.asyncio
async def test_agent_publishes_moteur_products(monkeypatch) -> None:
    async def fake_moteur_scrape(task):
        html = open("tests/fixtures/moteur_search.html", encoding="utf-8").read()
        return parse_products(html, task, page_url="https://www.moteur.ma/fr/voiture/achat-voiture-occasion/")

    _patch_other_providers_empty(monkeypatch)
    monkeypatch.setattr("agents.webscraping.agent.moteur.scrape", fake_moteur_scrape)
    producer = FakeProducer()
    agent = MockScraperAgent(config=MockScraperConfig(), producer=producer)

    products = await agent.handle_task(_task())

    assert len(products) == 1
    assert len(producer.published) == 1
    assert producer.published[0][1].source == "moteur"
