"""Executable HTTP boundary for payment risk decisions."""

from fastapi import FastAPI

from .risk_notifier import (
    GatewayNotificationWriter,
    PaymentEvent,
    RiskNotification,
    assess_payment,
)

service = FastAPI(title="Payment risk notifier")


@service.post("/payment-events/assess", response_model=RiskNotification)
def assess(event: PaymentEvent) -> RiskNotification:
    return assess_payment(event, GatewayNotificationWriter().draft)


def run() -> None:
    import uvicorn

    uvicorn.run("payment_risk_service.server:service", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
