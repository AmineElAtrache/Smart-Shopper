from agents.decision.tools.dedup_engine import deduplicate_products
from agents.decision.tools.fraud_detector import fraud_penalty
from agents.governance.rules.pii_scanner import find_pii, mask_pii
from agents.webscraping.tools.proxy_rotator import ProxyConfig, ProxyRotator
from shared.events.schemas import ProductQuery, RawProduct
from shared.runtime.metrics import MetricsRegistry


def test_pii_scanner_detects_and_masks_sensitive_values() -> None:
    text = "Contact me at test@example.com or 0612345678"

    assert find_pii(text) == ["email", "phone"]
    assert mask_pii(text) == "Contact me at [email] or [phone]"


def test_dedup_engine_removes_same_source_near_duplicate() -> None:
    products = [
        RawProduct(
            request_id="req_1",
            source="jumia",
            title="Samsung Galaxy A15 128GB",
            price=2499,
            url="https://example.com/1",
        ),
        RawProduct(
            request_id="req_1",
            source="jumia",
            title="Samsung Galaxy A15 128 GB",
            price=2500,
            url="https://example.com/2",
        ),
    ]

    assert len(deduplicate_products(products)) == 1


def test_fraud_penalty_flags_suspiciously_low_price() -> None:
    query = ProductQuery(product="phone", brand="Samsung", budget=3000)
    product = RawProduct(
        request_id="req_1",
        source="unknown",
        title="Samsung Galaxy A15",
        price=500,
        url="https://unknown.example/a15",
    )

    assert fraud_penalty(product, query) > 0


def test_proxy_rotator_cycles_weighted_proxies() -> None:
    rotator = ProxyRotator([ProxyConfig("http://one"), ProxyConfig("http://two")])

    assert rotator.next_proxy() == "http://one"
    assert rotator.next_proxy() == "http://two"
    assert rotator.next_proxy() == "http://one"


def test_metrics_registry_renders_prometheus_text() -> None:
    metrics = MetricsRegistry()
    metrics.increment("Smart Shopper Responses Total")
    metrics.gauge("Smart Shopper Queue Depth", 3)

    rendered = metrics.render_prometheus()

    assert "smart_shopper_responses_total 1" in rendered
    assert "smart_shopper_queue_depth 3" in rendered
