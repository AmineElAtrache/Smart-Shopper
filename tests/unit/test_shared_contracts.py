from shared.events import topics
from shared.events.kafka import decode_event, encode_event
from shared.events.schemas import Channel, InboundMessage


def test_topics_include_architecture_contracts() -> None:
    assert topics.MSG_INBOUND == "msg.inbound"
    assert topics.SCRAPE_TASK_ASSIGNED == "scrape.task.assigned"
    assert topics.DECISION_RANKED == "decision.ranked"
    assert topics.RESPONSE_OUTBOUND == "response.outbound"


def test_event_round_trip_json() -> None:
    event = InboundMessage(
        request_id="req_001",
        user_id="telegram_123",
        channel=Channel.TELEGRAM,
        text=" Samsung phone under 3000 MAD ",
    )

    decoded = decode_event(encode_event(event), InboundMessage)

    assert decoded.request_id == "req_001"
    assert decoded.text == "Samsung phone under 3000 MAD"
    assert decoded.channel == "telegram"
