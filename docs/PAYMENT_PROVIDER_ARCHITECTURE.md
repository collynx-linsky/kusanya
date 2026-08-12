# Payment Provider Architecture

**Status: implemented (Phase 3), mock provider only.** Code:
`apps/providers/`. No real provider is integrated — see build spec
section 43 and [compliance/REGULATORY_ASSUMPTIONS.md](compliance/REGULATORY_ASSUMPTIONS.md).

## The abstraction — implemented as `apps.providers.base.PaymentProviderAdapter`

The billing/payment engine never talks to a specific telecom or bank API
directly. It talks to this `ABC`:

```python
class PaymentProviderAdapter(ABC):
    def initiate_payment(self, *, amount, currency, control_number,
                          payer_reference, merchant_reference, metadata) -> ProviderResult: ...
    def query_payment(self, *, merchant_reference) -> ProviderResult: ...
    def validate_reference(self, *, control_number) -> bool: ...
    def process_callback(self, *, raw_payload, headers) -> ProviderCallbackResult: ...
    def refund(self, *, provider_reference, amount) -> ProviderResult: ...
    def reverse(self, *, provider_reference) -> ProviderResult: ...
    def reconcile(self, *, provider_reference) -> ProviderResult: ...
    def health_check(self) -> bool: ...
```

Every method returns/consumes a normalized vocabulary
(`ProviderOutcome`: `PENDING`/`SUCCESSFUL`/`FAILED`/`UNKNOWN`) — the
orchestrator (`apps.payments.services`, see
[PAYMENT_LIFECYCLE.md](PAYMENT_LIFECYCLE.md)) never sees a
provider-specific status code. `apps.providers.registry.get_adapter()`
is the **only** place `provider.code` maps to a concrete adapter class —
see [../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md) for why
this seam matters.

### Why `merchant_reference`, not just `provider_reference`

`initiate_payment()` requires KUSANYA to generate and pass in a
`merchant_reference` *before* calling the provider. This is what makes a
timeout recoverable at all: if the provider's response never arrives, we
never learn its `provider_reference` — but we always know our own
`merchant_reference`, and a real provider API accepts exactly this kind
of caller-supplied reference for later status queries. Querying by
anything the provider generated would be impossible for a lost response.

## What ships: `apps.providers.mock.MockPaymentProviderAdapter`

The only adapter in this codebase. Its outcome is controlled by
`metadata["mock_outcome"]` (`"successful"` default, `"failed"`,
`"pending"`, `"timeout"`) — every place it's used is unmistakably labeled
MOCK/SANDBOX (`PaymentProvider.is_sandbox=True`, `"SANDBOX"` suffix in
`__str__`, a warning banner on the portal's pay-bill page). The `"timeout"`
outcome specifically simulates a realistic scenario, not an arbitrary one:
the (simulated) provider actually processes the request successfully, but
the response is deliberately never returned to the caller — proving the
UNKNOWN-then-query flow against something real rather than only
documenting it. See `apps/providers/mock.py`'s module docstring for the
full honesty notes on what this does and doesn't prove about a real
integration.

`MockProviderTransaction` (`apps/providers/models.py`) is the mock's own
tiny internal transaction store — needed so `query_payment()` gives
consistent answers across process boundaries (a Celery worker and the
web process are different Python processes; in-memory state wouldn't be
shared between them). A real adapter has no equivalent — it calls the
actual provider's API.

## Callback signature verification

`process_callback()` verifies an HMAC-SHA256 signature
(`apps.core.signing`, shared with the outbound webhook signer) before
parsing anything — `InvalidCallbackSignatureError` is raised, and
`apps.payments.services.process_callback` turns that into a
`PaymentCallbackEvent.Outcome.INVALID_SIGNATURE` row without ever
touching payment state. A real provider adapter implements whatever
scheme that specific provider actually uses.

## Why no real provider yet

Unchanged from Phase 2's version of this document: build spec section 43
is explicit — do not invent provider APIs, do not fabricate credentials,
do not hard-code imaginary endpoints. Real adapters are built only once a
specific licensed provider is contracted and its official API
documentation and real credentials are available.

## `providers/aggregator/`

Still not implemented, still not planned speculatively — only added if
and when an aggregator integration is actually contracted.
