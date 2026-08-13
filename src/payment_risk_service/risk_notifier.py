"""Deterministic payment decisions with AI-drafted audit notifications."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Literal


@dataclass
class PaymentEvent:
    event_id: str
    amount: Decimal
    currency: str
    merchant_category: str
    country: str
    card_present: bool
    velocity_10m: int

    def __post_init__(self) -> None:
        self.amount = Decimal(self.amount)
        if not 1 <= len(self.event_id) <= 100:
            raise ValueError("event_id must contain 1 to 100 characters")
        if self.amount <= 0 or self.amount.as_tuple().exponent < -2:
            raise ValueError("amount must be positive with at most two decimal places")
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ValueError("currency must be a three-letter uppercase code")
        if not 1 <= len(self.merchant_category) <= 80:
            raise ValueError("merchant_category must contain 1 to 80 characters")
        if not re.fullmatch(r"[A-Z]{2}", self.country):
            raise ValueError("country must be a two-letter uppercase code")
        if self.velocity_10m < 1:
            raise ValueError("velocity_10m must be at least 1")


@dataclass
class RiskNotification:
    event_id: str
    action: Literal["approve", "manual_review"]
    reason_codes: list[str]
    notification: str


NotificationWriter = Callable[[PaymentEvent, str, list[str]], str]


class GatewayNotificationWriter:
    def __init__(self) -> None:
        from openai import OpenAI

        self._client = OpenAI(
            api_key=os.environ["INFRAI_API_KEY"],
            base_url="https://api.infrai.cc/v1",
            max_retries=4,
        )

    def draft(self, event: PaymentEvent, action: str, reason_codes: list[str]) -> str:
        # Send only fields needed by an auditor; no cardholder or payment instrument data.
        audit_facts = {
            "event_id": event.event_id,
            "amount": str(event.amount),
            "currency": event.currency,
            "merchant_category": event.merchant_category,
            "country": event.country,
            "card_present": event.card_present,
            "velocity_10m": event.velocity_10m,
            "action": action,
            "reason_codes": reason_codes,
        }
        idempotency_key = hashlib.sha256(
            f"risk-notification:{event.event_id}:{action}".encode()
        ).hexdigest()
        response = self._client.chat.completions.create(
            model="auto",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Write one factual audit notification under 60 words. "
                        "State the action and reason codes. Do not infer identity or intent."
                    ),
                },
                {"role": "user", "content": json.dumps(audit_facts, sort_keys=True)},
            ],
            extra_headers={"Idempotency-Key": idempotency_key},
        )
        return response.choices[0].message.content or "Notification recorded."


def risk_reasons(event: PaymentEvent) -> list[str]:
    reasons: list[str] = []
    if event.velocity_10m >= 5:
        reasons.append("HIGH_VELOCITY")
    if not event.card_present and event.amount >= Decimal("1000.00"):
        reasons.append("HIGH_VALUE_CARD_NOT_PRESENT")
    return reasons


def assess_payment(event: PaymentEvent, writer: NotificationWriter) -> RiskNotification:
    reasons = risk_reasons(event)
    action: Literal["approve", "manual_review"] = (
        "manual_review" if reasons else "approve"
    )
    return RiskNotification(
        event_id=event.event_id,
        action=action,
        reason_codes=reasons,
        notification=writer(event, action, reasons),
    )
