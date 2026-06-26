from agents.webscraping.agent import SCRAPE_PROVIDERS
from shared.memory.tier1_hooks import PROVIDER_DOMAINS


def test_scrape_providers_include_new_moroccan_sites() -> None:
    names = {name for name, _provider in SCRAPE_PROVIDERS}
    assert names == {
        "jumia",
        "avito",
        "electrosalam",
        "mafiawaystore",
        "moteur",
        "mymarket",
        "ultrapc",
        "electroplanet",
        "defacto",
        "biougnach",
        "marjane",
        "decathlon",
        "mubawab",
        "ikea",
        "palmarosa",
        "bringo",
        "planetsport",
    }
    assert len(SCRAPE_PROVIDERS) == 17


def test_tier1_provider_domains_include_new_sites() -> None:
    assert PROVIDER_DOMAINS["palmarosa"] == "www.palmarosashop.com"
    assert PROVIDER_DOMAINS["bringo"] == "www.bringo.ma"
    assert PROVIDER_DOMAINS["planetsport"] == "planetsport.ma"
