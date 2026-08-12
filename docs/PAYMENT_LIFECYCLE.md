# Payment Lifecycle

**Status: not yet implemented** (Phase 3). This document specifies the
payment state machine the payment engine must implement.

## States

```
INITIATED → PENDING → SUCCESSFUL
                │           
                ├────► FAILED
                ├────► UNKNOWN ──► (reconciliation) ──► SUCCESSFUL | FAILED
                └────► EXPIRED

SUCCESSFUL → REVERSED
SUCCESSFUL → REFUNDED
```

## The rule that matters most: a timeout is not a failure

If a request to a payment provider times out, the payment becomes
`UNKNOWN` — never automatically `FAILED`. The provider may have actually
processed the payment; declaring it failed and letting the customer pay
again risks a double-charge with no correction path.

**Required behavior on `UNKNOWN`:**

1. Never blindly retry the payment.
2. Query the provider (`PaymentProviderAdapter.query_payment()`, see
   [PAYMENT_PROVIDER_ARCHITECTURE.md](PAYMENT_PROVIDER_ARCHITECTURE.md))
   to find out what actually happened before deciding anything.
3. Only after that query resolves the true state does the payment
   transition to `SUCCESSFUL` or `FAILED` — reconciliation
   ([RECONCILIATION_SPEC.md](RECONCILIATION_SPEC.md)) is the backstop for
   payments that stay `UNKNOWN` because even the query is inconclusive.

## Orchestrator responsibilities (Phase 3)

The Payment Orchestrator owns provider selection/routing, availability
checks, timeout handling, retry policy, idempotency, status
normalization (mapping each provider's own status vocabulary onto this
document's states), callback processing, reconciliation triggers, and
provider health tracking. It must not switch providers mid-flight for an
`UNKNOWN` payment without first checking that provider's own state for
that payment — silently retrying against a different provider risks a
double payment the customer only discovers later.

## Idempotency at every step

Payment initiation, provider callbacks, refunds, and reversals must all
be idempotent (build spec section 14): the same provider webhook
delivered three times must produce exactly one financial event, not
three. This is a Phase 3 test requirement, not just an implementation
detail — see [TESTING.md](TESTING.md).
