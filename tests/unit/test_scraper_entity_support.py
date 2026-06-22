from pathlib import Path

from agents.webscraping.spiders import biougnach, electroplanet, ikea, mubawab
from shared.events.schemas import Channel, ProductQuery, ScrapeTaskAssigned


def _task(query: ProductQuery) -> ScrapeTaskAssigned:
    return ScrapeTaskAssigned(
        request_id="req_entity_support",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        query=query,
    )


def test_non_avito_providers_filter_with_product_brand_and_budget() -> None:
    html = Path("tests/fixtures/electroplanet_search.html").read_text(encoding="utf-8")
    task = _task(ProductQuery(product="phone", brand="Samsung", budget=3000))

    products = electroplanet.parse_products(
        html,
        task,
        page_url="https://www.electroplanet.ma/catalogsearch/result/?q=Samsung+phone",
    )

    assert len(products) == 2
    assert all(product.source == "electroplanet" for product in products)
    assert all("Samsung" in product.title for product in products)
    assert all(product.price <= 3750 for product in products)


def test_non_avito_providers_filter_with_color_aliases() -> None:
    html = Path("tests/fixtures/ikea_search.html").read_text(encoding="utf-8")
    task = _task(ProductQuery(product="chair", color="black", budget=600))

    products = ikea.parse_products(
        html,
        task,
        page_url="https://www.ikea.com/ma/fr/search/?q=chaise+noir",
    )

    assert len(products) == 1
    assert products[0].title == "STEFAN Chaise brun-noir"


def test_category_shortcut_providers_still_filter_color_after_fetch() -> None:
    html = Path("tests/fixtures/biougnach_search.html").read_text(encoding="utf-8")
    task = _task(ProductQuery(product="Smartphone", brand="Samsung", color="black", budget=3000))

    products = biougnach.parse_products(
        html,
        task,
        page_url="https://www.biougnach.ma/shop/category/-50/4",
    )

    assert len(products) == 0


def test_city_provider_filters_city_and_budget() -> None:
    html = Path("tests/fixtures/mubawab_search.html").read_text(encoding="utf-8")
    task = _task(ProductQuery(product="apartment", city="casablanca", budget=1200000))

    products = mubawab.parse_products(
        html,
        task,
        page_url="https://www.mubawab.ma/fr/st/casablanca/appartements-a-vendre",
    )

    assert len(products) == 2
    assert all(product.price <= 1500000 for product in products)
