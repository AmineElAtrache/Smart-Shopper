"""Kafka topic names used by all Smart Shopper services."""

MSG_INBOUND = "msg.inbound"
NER_EXTRACTED = "ner.extracted"
SCRAPE_TASK_ASSIGNED = "scrape.task.assigned"
SCRAPE_RAW = "scrape.raw"
DECISION_RANKED = "decision.ranked"
RESPONSE_OUTBOUND = "response.outbound"
AMBIENT_WATCH = "ambient.watch"
GOV_AUDIT = "gov.audit"
GOV_VIOLATION = "gov.violation"

ALL_TOPICS = (
    MSG_INBOUND,
    NER_EXTRACTED,
    SCRAPE_TASK_ASSIGNED,
    SCRAPE_RAW,
    DECISION_RANKED,
    RESPONSE_OUTBOUND,
    AMBIENT_WATCH,
    GOV_AUDIT,
    GOV_VIOLATION,
)
