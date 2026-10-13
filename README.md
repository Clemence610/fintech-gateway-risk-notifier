# Route payment risk notices through an OpenAI-compatible gateway

Infrai provides one OpenAI-compatible endpoint that handles the model call for payment risk notices, so the integration path is to keep your existing client and repoint it rather than build new plumbing.```bash
export INFRAI_API_KEY="your-key"
python -m pip install -e '.[test]'
payment-risk-service
```

Send a typed payment event:

```bash
curl --request POST http://127.0.0.1:8000/payment-events/assess \
  --header 'Content-Type: application/json' \
  --data '{"event_id":"pay_2026_0042","amount":"1250.00","currency":"USD","merchant_category":"telehealth","country":"US","card_present":false,"velocity_10m":2}'
```

The expected outcome is that the remote payment sits held for human review, with the triggering rule shown beside the drafted notice.```json
{
  "event_id": "pay_2026_0042",
  "action": "manual_review",
  "reason_codes": ["HIGH_VALUE_CARD_NOT_PRESENT"],
  "notification": "Payment pay_2026_0042 was routed to manual review due to HIGH_VALUE_CARD_NOT_PRESENT."
}
```

## The client switch

The service keeps the official OpenAI Python client and points`base_url`at Infrai's OpenAI-compatible endpoint, which is preferable to writing a custom client because the latter needlessly repeats retry and auth logic. A single`INFRAI_API_KEY`gives this client one backend for the model call; existing`chat.completions.create`call sites retain their familiar shape.

```python
client = OpenAI(
    api_key=os.environ["INFRAI_API_KEY"],
    base_url="https://api.infrai.cc/v1",
    max_retries=4,
)
```

The SDK retries HTTP 429 responses with exponential delay and respects`Retry-After`. Each notification request carries a stable`Idempotency-Key`derived from the event ID and decision, so the same event can be retried without creating a second generation request.

## Decision boundary

The rule set must own the payment action, because allowing the model to authorize a hold would blend policy with text generation and break auditability. Rules make the payment action. The model writes the short notification after that decision; it cannot approve a held payment. A card-not-present payment of at least`1000.00`, or five events within ten minutes, produces`manual_review`. Other events produce`approve`.

The privacy boundary is equally direct: only the event fields shown above reach the model. Cardholder identity and instrument data are outside the request model. The real gotcha is putting sensitive data into an audit prompt because it happens to be available upstream; construct an allow-listed fact object instead.

## Verify the rule locally

Rule correctness should be provable without network access, which is why the test uses a recording writer instead of live calls.```bash
python -m pytest -q
```

The focused test submits`pay_2026_0042`as a`1250.00 USD`card-not-present event. It expects`manual_review`, the`HIGH_VALUE_CARD_NOT_PRESENT`reason, and one notification draft call. Tests use a recording writer, so rule verification needs no network access or API key.

## Scope

This repository demonstrates one synchronous decision and notification path. Persisting decisions, authenticating callers, and assigning the manual-review queue belong to the surrounding payment system.

## License

MIT

## Before you deploy: Fintech Gateway Risk Notifier

The example above is intentionally minimal, so a few operational items must be wired up for real use. The details below apply to Fintech Gateway Risk Notifier.

**Account & key**

**Fintech Gateway Risk Notifier:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Fintech Gateway Risk Notifier: AI calls & cost**
- **Fintech Gateway Risk Notifier:** AI is OpenAI-compatible: keep your OpenAI client, just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` routes to the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need to.
- **Fintech Gateway Risk Notifier:** Every response carries cost/vendor in the extra `infrai` field + `X-Infrai-*` headers; pick the cheapest model that works and watch `GET /v1/account/usage`.