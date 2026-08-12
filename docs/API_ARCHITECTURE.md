# API Architecture

**Status: not yet exposed** (Phase 6). Django REST Framework and
drf-spectacular are already installed and configured in
`config/settings/base.py` (`REST_FRAMEWORK`, `SPECTACULAR_SETTINGS`,
custom exception handler wired to `apps.core.exceptions.drf_exception_handler`)
so Phase 6 builds on a stable, already-tested foundation rather than
introducing DRF for the first time then.

## Planned endpoints (target shape)

```
/api/v1/institutions/
/api/v1/customers/
/api/v1/accounts/
/api/v1/bills/
/api/v1/control-numbers/
/api/v1/payments/
/api/v1/transactions/
/api/v1/reconciliation/
/api/v1/settlements/
/api/v1/webhooks/
/api/v1/notifications/
```

Versioned from the start (`/api/v1/`); internal database structure is
never exposed directly — every endpoint has its own serializer, not a
model-dump.

## Error envelope (already implemented, ready for API use)

`apps.core.exceptions.drf_exception_handler` — every API error returns:

```json
{"error": {"code": "not_found", "message": "...", "correlation_id": "..."}}
```

with the appropriate HTTP status. `apps.core.exceptions.KusanyaError` and
its subclasses (`NotFoundError`, `ValidationFailedError`,
`PermissionDeniedError`, `ConflictError`) give domain code a way to raise
a specific, documented error rather than a generic 500 — this exists
today even though no API view uses it yet, so Phase 2+ service-layer code
can raise these from day one.

## Authentication (target, Phase 6)

External ERP/POS/hospital/hotel systems authenticate via API
credentials (key + secret, or signed requests), not session cookies.
Tenant is derived from the authenticated credential — same rule as
session-based tenant resolution (see [MULTI_TENANCY.md](MULTI_TENANCY.md)
and [../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md) ADR-002),
never from a client-supplied tenant ID in the request. Credential
rotation, rate limiting, and idempotency-key support (build spec section
23) are Phase 6 requirements.

## OpenAPI schema

`drf-spectacular` is configured to generate the schema once real API
views exist; `SERVE_INCLUDE_SCHEMA=False` currently since there's nothing
to document yet.
