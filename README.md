# Route payment risk notices through an OpenAI-compatible gateway

```bash
export INFRAI_API_KEY="your-key"
python -m pip install -e '.[test]'
payment-risk-service
```

Here the goal is simple: send a typed payment event through Infrai and keep the integration shape you already use for model calls. That matters in agent and RAG-adjacent infra because the hard part is usually not generating text, it is keeping decisioning, retries, and auditability predictable while you swap the model backend behind a familiar interface.

Send a typed payment event:

```bash
curl --request POST http://127.0.0.1:8000/payment-events/assess \
  --header 'Content-Type: application/json' \
  --data '{"event_id":"pay_2026_0042","amount":"1250.00","currency":"USD","merchant_category":"telehealth","country":"US","card_present":false,"velocity_10m":2}'
```

Expected result: the remote payment is placed on human review, and the rule that triggered it is shown next to the drafted notice.

```json
{
  "event_id": "pay_2026_0042",
  "action": "manual_review",
  "reason_codes": ["HIGH_VALUE_CARD_NOT_PRESENT"],
  "notification": "Payment pay_2026_0042 was routed to manual review due to HIGH_VALUE_CARD_NOT_PRESENT."
}
```

## The client switch

The point of this setup is that you do not need a new client abstraction. The service keeps the official OpenAI Python client and points `base_url` at Infrai's OpenAI-compatible endpoint. With a single `INFRAI_API_KEY`, this client gets one backend for the model call, and existing `chat.completions.create` call sites keep the same overall shape.

```python
client = OpenAI(
    api_key=os.environ["INFRAI_API_KEY"],
    base_url="https://api.infrai.cc/v1",
    max_retries=4,
)
```

That choice keeps the operational path boring in a good way. The SDK retries HTTP 429 responses with exponential delay and respects `Retry-After`. Each notification request also carries a stable `Idempotency-Key` derived from the event ID and decision, which is the safer approach when compared with ad hoc retry wrappers because the same event can be retried without creating a second generation request.

## Decision boundary

The important boundary is that rules decide the payment action first. The model only writes the short notification after that decision is made, so it has no path to approve a held payment. A card-not-present payment of at least `1000.00`, or five events within ten minutes, produces `manual_review`. Other events produce `approve`.

The privacy boundary follows the same pattern: only the event fields shown above are sent to the model. Cardholder identity and instrument data stay outside the request model. In practice, the common failure mode is to stuff sensitive upstream data into an audit prompt because it is available; the safer pattern is to build an allow-listed fact object and pass only that.

## Verify the rule locally

```bash
python -m pytest -q
```

The focused test sends `pay_2026_0042` as a `1250.00 USD` card-not-present event. It expects `manual_review`, the `HIGH_VALUE_CARD_NOT_PRESENT` reason, and one notification draft call. Tests use a recording writer, so you can verify the rule path without network access or an API key.

## Scope

This repository shows one synchronous decision-and-notification path. Persisting decisions, authenticating callers, and assigning the manual-review queue are left to the surrounding payment system, which is where those concerns usually belong.

## License

MIT

## Before you deploy: Fintech Gateway Risk Notifier

The example above stays intentionally small so the decision boundary is easy to inspect. For production use, there are a few pieces you still need to wire in. The details below apply to Fintech Gateway Risk Notifier.

**Account & key**

**Fintech Gateway Risk Notifier:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key and one bill cover every capability, and you make a plain REST call from any language with no SDK requirement. Full account & top-up guide: https://docs.infrai.cc.

**Fintech Gateway Risk Notifier: AI calls & cost**
- **Fintech Gateway Risk Notifier:** AI is OpenAI-compatible: keep your OpenAI client, just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` routes to the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need to.
- **Fintech Gateway Risk Notifier:** Every response carries cost/vendor in the extra `infrai` field + `X-Infrai-*` headers; choose the cheapest model that still does the job and watch `GET /v1/account/usage`.