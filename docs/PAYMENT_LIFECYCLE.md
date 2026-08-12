# Payment Lifecycle

**Status: implemented (Phase 3).** Code: `apps/payments/`. This document
specifies the payment state machine and records what the implementation
actually does — verified both by 22 automated tests
(`apps/payments/tests/tests.py`) and a manual end-to-end run over real
HTTP with a real Celery worker during Phase 3 development.

## States

```text
INITIATED → PENDING → SUCCESSFUL
                │           
                ├────► FAILED
                ├────► UNKNOWN ──► (query_payment) ──► SUCCESSFUL | FAILED
                └────► EXPIRED

SUCCESSFUL → REVERSED
SUCCESSFUL → REFUNDED
```

**Implemented as** `apps.payments.models.Payment.transition_to()`,
enforcing an explicit `ALLOWED_TRANSITIONS` table — the same
model-layer-enforcement pattern already used for `Bill`
(`docs/BILLING_SPEC.md`) and `AuditLog`
(`../ARCHITECTURE_DECISIONS.md` ADR-006). An invalid jump raises
`ValidationError`, not a silent status overwrite.

## The rule that matters most: a timeout is not a failure

If a request to a payment provider times out, the payment becomes
`UNKNOWN` — never automatically `FAILED`. The provider may have actually
processed the payment; declaring it failed and letting the customer pay
again risks a double-charge with no correction path.

**Implemented behavior on timeout:**

1. `apps.providers.base.ProviderTimeoutError`, raised by an adapter, is
   caught specifically by `apps.payments.services.initiate_payment` and
   results in `Payment.status = UNKNOWN` — there is no code path from a
   provider timeout to `FAILED`.
2. Nothing retries automatically. `initiate_payment()` is never called
   again for an `UNKNOWN` payment by any code in this codebase.
3. The only way an `UNKNOWN` payment resolves is
   `apps.payments.services.query_payment()`, which asks the provider
   adapter's `query_payment(merchant_reference=...)` — keyed by KUSANYA's
   own `merchant_reference`, generated *before* the provider call and
   therefore known regardless of whether the provider's response ever
   arrived (see [PAYMENT_PROVIDER_ARCHITECTURE.md](PAYMENT_PROVIDER_ARCHITECTURE.md)).
   Tested explicitly: `TestPaymentTimeoutHandling` proves a timed-out
   payment that actually succeeded server-side resolves to `SUCCESSFUL`
   on query, allocates to its bill, and does **not** create a second
   `Payment` row or a second allocation even if queried twice.

Reconciliation (Phase 4, [RECONCILIATION_SPEC.md](RECONCILIATION_SPEC.md))
remains the scheduled backstop for payments that stay `UNKNOWN` because
even an explicit query is inconclusive — not yet built, since it depends
on the ledger.

## Payment Orchestrator — what's implemented

`apps.payments.services` owns: provider routing (via
`apps.providers.registry.get_adapter`), idempotent initiation
(`idempotency_key`), status normalization (every adapter maps its own
vocabulary onto `apps.providers.base.ProviderOutcome`, which the
orchestrator translates to `PaymentStatus`), inbound callback processing,
refunds, and reversals. **Not yet implemented:** provider health-based
routing/failover (moot with exactly one provider registered) and
scheduled reconciliation (Phase 4).

## Idempotency — implemented at every step named in the build spec

- **Initiation:** `initiate_payment(..., idempotency_key=...)` — a
  repeat call with the same key returns the existing `Payment` without
  contacting the provider again. Tested.
- **Callbacks:** `apps.payments.models.PaymentCallbackEvent` has a
  `UniqueConstraint(provider, external_event_id)` — the *same provider
  event* delivered three times is rejected at the database level after
  the first delivery, before any status transition or webhook dispatch
  happens. Tested directly:
  `test_same_event_delivered_three_times_produces_one_financial_event`
  asserts exactly one `PaymentAllocation` and one paid bill after three
  identical deliveries.
- **Status-equality no-op:** independently of the event-ID constraint,
  `apps.payments.services._apply_outcome()` is a no-op if the payment is
  already in the target status — so even a callback with a *new* event ID
  reporting an *already-applied* outcome (e.g. two different provider
  event IDs both claiming SUCCESSFUL) doesn't double-fire the
  `payment.successful` audit event or webhook.
- **Refunds/reversals:** guarded by requiring `status == SUCCESSFUL`
  before attempting either — calling refund/reverse on anything else
  raises `ValidationError` rather than silently no-opping or double-
  processing.

## Signature verification on inbound callbacks

`apps.providers.mock.MockPaymentProviderAdapter.process_callback()`
verifies an HMAC-SHA256 signature (`apps.core.signing`) before parsing
the payload at all — an invalid signature never reaches payment logic
(`PaymentCallbackEvent.Outcome.INVALID_SIGNATURE`, tested). A real
provider adapter implements whatever signature scheme that provider
actually uses; the requirement — verify before processing — is the same.

## What's still not built (depends on later phases)

Multi-bill allocation for persistent (account-bound) control numbers
(needs Phase 4's ledger to decide an allocation order, e.g.
oldest-bill-first); scheduled reconciliation of stuck `UNKNOWN` payments
(Phase 4); receipts (Phase 5); the external API surface for ERPs to
initiate/query payments themselves (Phase 6) — the portal
(`apps.payments.views`) is the only caller today.
