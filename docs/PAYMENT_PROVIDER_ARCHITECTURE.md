# Payment Provider Architecture

**Status: not yet implemented** (Phase 3). This document specifies the
provider abstraction; no real provider is integrated until official
documentation and credentials exist for one — see build spec section 43
and [compliance/REGULATORY_ASSUMPTIONS.md](compliance/REGULATORY_ASSUMPTIONS.md).

## The abstraction

The billing/payment engine never talks to a specific telecom or bank API
directly. It talks to a `PaymentProviderAdapter` interface:

```
PaymentProviderAdapter:
    initiate_payment()
    query_payment()
    validate_reference()
    process_callback()
    refund()
    reverse()
    reconcile()
    health_check()
```

Each real provider gets its own adapter under `providers/<provider_name>/`
implementing this interface; the orchestrator
([PAYMENT_LIFECYCLE.md](PAYMENT_LIFECYCLE.md)) only ever calls the
interface, never a provider-specific method.

## What ships in Phase 3: a mock/sandbox provider only

`providers/mock/` implements the same interface against no real network
call — configurable to simulate success, failure, timeout/`UNKNOWN`, and
provider-side delay, so the payment lifecycle and orchestrator can be
built and tested completely before any real provider is integrated. Every
place this mock is used is clearly labeled MOCK/SANDBOX in logs, UI, and
API responses — it must never be possible to mistake a mock payment for a
real one (build spec section 44).

## Why no real provider yet

Build spec section 43 is explicit: do not invent provider APIs, do not
fabricate credentials, do not hard-code imaginary endpoints. Real adapters
are implemented once official API documentation and real
sandbox/production credentials are available for a specific licensed
provider — until then, any "integration" would be fictional and would
misrepresent the platform's actual capabilities.

## Aggregator adapters

`providers/aggregator/` is reserved for a future adapter that itself
routes to multiple underlying providers (useful if KUSANYA integrates
with a payment aggregator rather than each channel individually) — not
implemented in Phase 3 by default, added only if/when such an integration
is actually contracted.
