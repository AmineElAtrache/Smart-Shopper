"""Kafka topic names used by all Smart Shopper services."""

MSG_INBOUND = "msg.inbound"
NER_EXTRACTED = "ner.extracted"
SCRAPE_TASK_ASSIGNED = "scrape.task.assigned"
SCRAPE_RAW = "scrape.raw"
DECISION_RANKED = "decision.ranked"
RESPONSE_OUTBOUND = "response.outbound"
AMBIENT_WATCH = "ambient.watch"
AMBIENT_TICK = "ambient.tick"
PRICE_HISTORY = "price.history"
CACHE_WRITE = "cache.write"
GOV_AUDIT = "gov.audit"
GOV_VIOLATION = "gov.violation"
ERROR_DEAD_LETTER = "error.dead_letter"

ALL_TOPICS = (
    MSG_INBOUND,
    NER_EXTRACTED,
    SCRAPE_TASK_ASSIGNED,
    SCRAPE_RAW,
    DECISION_RANKED,
    RESPONSE_OUTBOUND,
    AMBIENT_WATCH,
    AMBIENT_TICK,
    PRICE_HISTORY,
    CACHE_WRITE,
    GOV_AUDIT,
    GOV_VIOLATION,
    ERROR_DEAD_LETTER,
)
