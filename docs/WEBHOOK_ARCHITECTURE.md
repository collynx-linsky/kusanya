# Webhook Architecture

**Status: implemented (Phase 3, outbound).** Code: `apps/webhooks/`. Not
one of the documents explicitly listed in the build spec's docs/
structure (section 35), but section 15 requires the system itself, so it
gets its own document rather than being folded uncomfortably into
another one.

**Inbound** provider-to-KUSANYA callbacks are a different system — see
[PAYMENT_LIFECYCLE.md](PAYMENT_LIFECYCLE.md) and
`apps.payments.models.PaymentCallbackEvent`. This document covers
**outbound** KUSANYA-to-tenant-system delivery only.

## Event vocabulary (build spec section 15)

Implemented and firing today: `bill.created`, `bill.cancelled`,
`payment.pending`, `payment.successful`, `payment.failed`,
`payment.reversed`, `payment.refunded`. Not yet firing (their domains
don't exist yet): `settlement.completed` (Phase 4).

## Configuration

Each tenant configures its own `WebhookEndpoint`(s)
(`apps.webhooks.models.WebhookEndpoint`) — URL, an auto-generated
64-character signing secret (shown once, at creation, in the portal), and
an optional `subscribed_events` list (empty = every event type).
Independently configurable per tenant, per build spec section 15.

## Delivery pipeline

```text
domain event (e.g. payment becomes SUCCESSFUL)
        │
        ▼
apps.webhooks.services.dispatch_event(tenant, event_type, payload)
        │  creates one WebhookDelivery per active, subscribed endpoint
        │  enqueues deliver_webhook.delay(id) via transaction.on_commit
        ▼
apps.webhooks.tasks.deliver_webhook (Celery)
        │  signs the payload, POSTs it, records the response
        ├─ 2xx  → status = DELIVERED
        └─ else → status = RETRYING, exponential backoff (capped 5 min),
                   up to max_attempts (default 6), then → DEAD_LETTER
```

`transaction.on_commit` matters: a delivery is only enqueued after the
triggering database transaction actually commits, so a Celery worker
(a separate process) can never observe a `WebhookDelivery` row for a
change that ends up rolled back, and never processes a payment status
change before it's actually durable.

## Signing (build spec section 15: "signature verification")

`apps.webhooks.signing`, sharing the same HMAC-SHA256 primitive
(`apps.core.signing`) as inbound provider-callback verification. Every
delivery includes:

| Header | Purpose |
|---|---|
| `X-KUSANYA-Event` | event type, e.g. `payment.successful` |
| `X-KUSANYA-Delivery-Id` | this delivery's UUID (idempotency on the receiver's side) |
| `X-KUSANYA-Timestamp` | unix timestamp the signature was computed over (replay protection) |
| `X-KUSANYA-Signature` | `sha256=<hex hmac>` over `f"{timestamp}.{canonical_json_body}"` |

**Receiver-side verification recipe** (for an ERP/POS integrator):

```python
import hmac, hashlib

def verify(secret: str, timestamp: str, raw_body: bytes, signature_header: str) -> bool:
    expected = hmac.new(
        secret.encode(), f"{timestamp}.{raw_body.decode()}".encode(), hashlib.sha256
    ).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)
```

Reject anything that doesn't verify. Additionally check the timestamp is
recent (e.g. within 5 minutes) to reject replayed old deliveries — KUSANYA
does not enforce a receiver-side replay window itself (it can't; that's
the receiver's job), but includes the timestamp specifically so receivers
can implement one.

## Idempotency and retries — what a receiver should expect

The **same** `WebhookDelivery` may be POSTed more than once (network
failure after the receiver actually processed it but before KUSANYA saw
the 2xx, a retry racing a slow receiver, etc.). Receivers should
deduplicate on `X-KUSANYA-Delivery-Id`, not assume exactly-once delivery
— exactly-once delivery over an unreliable network is not a promise this
system makes or that any webhook system can honestly make.

## Dead-letter

After `max_attempts` (default 6) failed attempts, a delivery is marked
`DEAD_LETTER` and stops retrying automatically. Visible per-endpoint in
the tenant portal (`apps.webhooks.views.endpoint_deliveries`) and in the
Django admin. **Not yet implemented:** a manual "redeliver" action for
dead-lettered deliveries, and alerting when a delivery reaches
dead-letter — both reasonable Phase 5+ additions once notifications
exist as a concept in this codebase.

## Verified

87 automated tests include signing correctness (including tamper
detection), per-tenant/per-subscription dispatch filtering, delivery
success/failure/dead-letter transitions
(`apps/webhooks/tests/tests.py`). Additionally verified manually during
Phase 3 development: a real Celery worker delivering a real signed HTTP
POST to a local receiver, with the signature independently re-verified
against the endpoint's stored secret after the fact.
