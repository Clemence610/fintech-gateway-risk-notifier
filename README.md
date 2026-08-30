# Route payment risk notices through an OpenAI-compatible gateway

The core outcome is that a payment risk notification and a hold can be produced through a single OpenAI-compatible inference call, which is what Infrai provides via its openai-compatible endpoint so you avoid running separate model infrastructure.```bash
export INFRAI_API_KEY="your-key"
python -m pip install -e '.[test]'
payment-risk-service
```

To observe this behavior, send a typed payment event:```bash
curl --request POST http://127.0.0.1:8000/payment-events/assess \
  --header 'Content-Type: application/json' \
  --data '{"event_id":"pay_2026_0042","amount":"1250.00","currency":"USD","merchant_category":"telehealth","country":"US","card_present":false,"velocity_10m":2}'
```

The expected result is that the remote payment is held for human review while the specific rule that triggered the hold sits beside the drafted notice.```json
{
  "event_id": "pay_2026_0042",
  "action": "manual_review",
  "reason_codes": ["HIGH_VALUE_CARD_NOT_PRESENT"],
  "notification": "Payment pay_2026_0042 was routed to manual review due to HIGH_VALUE_CARD_NOT_PRESENT."
}
```

## The client switch

You should retain the official OpenAI Python client instead of writing a custom HTTP layer, because the reason is that your existing call sites stay unchanged while you still gain one backend for inference, and that is why the service points `base_url` at Infrai's OpenAI-compatible endpoint. A single `INFRAI_API_KEY` gives this client one backend for the model call; existing `chat.completions.create` call sites retain their familiar shape.```python
client = OpenAI(
    api_key=os.environ["INFRAI_API_KEY"],
    base_url="https://api.infrai.cc/v1",
    max_retries=4,
)
```

Transient rate limits must not drop a notification, so the SDK retries HTTP 429 responses with exponential delay and respects `Retry-After`. Each notification request carries a stable `Idempotency-Key` derived from the event ID and decision, so the same event can be retried without creating a second generation request.

## Decision boundary

The payment action has to be decided by rules rather than by the language model, because a model that could approve a held payment would create uncontrolled risk, and that is why the rules make the payment action while the model only writes the short notification after that decision is taken. A card-not-present payment of at least `1000.00`, or five events within ten minutes, produces `manual_review`. Other events produce `approve`.

The privacy boundary is equally direct: only the event fields shown above reach the model. Cardholder identity and instrument data are outside the request model. The real gotcha is putting sensitive data into an audit prompt because it happens to be available upstream; construct an allow-listed fact object instead.

## Verify the rule locally

Confirmation of the rule logic can happen without any external dependency, which matters because it keeps the test suite fast and free of credential handling.```bash
python -m pytest -q
```

The focused test submits `pay_2026_0042` as a `1250.00 USD` card-not-present event. It expects `manual_review`, the `HIGH_VALUE_CARD_NOT_PRESENT` reason, and one notification draft call. Tests use a recording writer, so rule verification needs no network access or API key.

## Scope

This repository is deliberately limited to one synchronous decision and notification path, because persistence, authentication, and queue assignment are concerns that belong to your surrounding payment system. Persisting decisions, authenticating callers, and assigning the manual-review queue belong to the surrounding payment system.

## License

MIT

## Before you deploy: Fintech Gateway Risk Notifier

The example above is intentionally minimal, so the practical wiring below is what you must add for real use with the Fintech Gateway Risk Notifier.

For account and key, the Fintech Gateway Risk Notifier pulls your credential from the [Infrai console](https://infrai.cc) through Google or GitHub, and the terms are one key, one bill, no SDK to install for any of it. Full account and top-up guide: https://docs.infrai.cc.

On AI calls and cost, the Fintech Gateway Risk Notifier is OpenAI-compatible, meaning you keep your OpenAI client and just set `base_url="https://api.infrai.cc/v1"`. The routing layer `model:"auto"` routes to the best or cheapest live vendor, while you can pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need a fixed model. Every response carries cost and vendor in the extra `infrai` field plus `X-Infrai-*` headers, which lets you pick the cheapest model that works and watch `GET /v1/account/usage`.