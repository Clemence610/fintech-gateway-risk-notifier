from decimal import Decimal

from payment_risk_service.risk_notifier import PaymentEvent, assess_payment


class RecordingWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def draft(self, event: PaymentEvent, action: str, reason_codes: list[str]) -> str:
        self.calls.append((action, reason_codes))
        return f"Event {event.event_id}: {action}; {','.join(reason_codes)}"


def test_high_value_remote_payment_is_sent_to_manual_review() -> None:
    event = PaymentEvent(
        event_id="pay_2026_0042",
        amount=Decimal("1250.00"),
        currency="USD",
        merchant_category="telehealth",
        country="US",
        card_present=False,
        velocity_10m=2,
    )
    writer = RecordingWriter()

    result = assess_payment(event, writer.draft)

    assert result.action == "manual_review"
    assert result.reason_codes == ["HIGH_VALUE_CARD_NOT_PRESENT"]
    assert writer.calls == [("manual_review", ["HIGH_VALUE_CARD_NOT_PRESENT"])]
    assert "pay_2026_0042" in result.notification


def test_low_value_present_payment_is_approved() -> None:
    event = PaymentEvent(
        event_id="pay_2026_0043",
        amount=Decimal("48.25"),
        currency="USD",
        merchant_category="clinic",
        country="US",
        card_present=True,
        velocity_10m=1,
    )
    writer = RecordingWriter()

    result = assess_payment(event, writer.draft)

    assert result.action == "approve"
    assert result.reason_codes == []
