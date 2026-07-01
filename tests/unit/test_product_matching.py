from shared.product_matching import is_implausible_accessory_price, matches_category_product


def test_rejects_galaxy_smarttag_for_phone_query() -> None:
    title = "SAMSUNG GALAXY SMARTTAG2 WHITE"
    assert not matches_category_product(title, "phone", loose_aliases={"galaxy", "samsung"})


def test_accepts_galaxy_phone_model() -> None:
    title = "Samsung Galaxy A15 128GB Blanc"
    assert matches_category_product(title, "phone", loose_aliases={"galaxy", "samsung"})


def test_implausible_accessory_price_filters_cheap_non_phones() -> None:
    assert is_implausible_accessory_price(
        title="SAMSUNG GALAXY SMARTTAG2 WHITE",
        url="https://example.com/smarttag",
        price=249,
        category="phone",
        budget=3000,
        loose_aliases={"galaxy"},
    )


def test_implausible_accessory_price_keeps_real_budget_phones() -> None:
    assert not is_implausible_accessory_price(
        title="Itel A100C 6,6 - 2+4 RAM + 64 ROM",
        url="https://example.com/itel",
        price=879,
        category="phone",
        budget=3000,
        loose_aliases={"itel"},
    )
