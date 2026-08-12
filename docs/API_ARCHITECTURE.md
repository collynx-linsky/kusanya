# API Architecture

**Status: implemented (Phase 6).** Code: `apps/api/`. Django REST
Framework and drf-spectacular were wired in Phase 1 specifically so this
phase would build on an already-tested foundation rather than
introducing DRF for the first time here — that bet paid off; no
framework-level changes were needed, only real views.

## Endpoints — implemented

```text
GET  /api/v1/institutions/me/
GET  /api/v1/customers/                    POST /api/v1/customers/
GET  /api/v1/customers/{id}/
GET  /api/v1/accounts/                     POST /api/v1/accounts/
GET  /api/v1/bills/                        POST /api/v1/bills/
GET  /api/v1/bills/{id}/
POST /api/v1/bills/{id}/control-number/
GET  /api/v1/payments/                     POST /api/v1/payments/
GET  /api/v1/payments/{id}/
POST /api/v1/payments/{id}/query/
GET  /api/v1/reconciliation/
GET  /api/v1/settlements/
GET  /api/v1/settlements/{id}/
GET  /api/v1/webhooks/                     POST /api/v1/webhooks/
GET  /api/v1/notifications/
GET  /api/schema/                          (OpenAPI 3 schema, JSON)
GET  /api/docs/                            (interactive Swagger UI)
```

**`/api/v1/transactions/` was deliberately not built as a separate
route.** Build spec section 22 names "query transaction" as a distinct
ERP-integration capability, but a "transaction" in that vocabulary is
exactly what this codebase calls a `Payment` — exposing two URLs
returning the same data under different names would create ambiguity
about which is canonical, not add capability. `GET /api/v1/payments/{id}/`
*is* the transaction-query endpoint.

Versioned from the start (`/api/v1/`). Every endpoint has its own
hand-written serializer (`apps/api/serializers.py`) — never
`fields = "__all__"` — so internal database structure is never exposed
by accident.

## The one rule every write endpoint follows

**No endpoint calls `serializer.save()`.** Every write (`POST
/customers/`, `/accounts/`, `/bills/`, `/bills/{id}/control-number/`,
`/payments/`) calls the exact same service-layer function the
server-rendered portal calls —
`apps.customers.services.get_or_create_customer`,
`apps.billing.services.get_or_create_bill`,
`apps.control_numbers.services.get_or_create_for_bill`,
`apps.payments.services.initiate_payment`. This is what makes API-
originated idempotency, audit logging, revenue events, ledger entries,
webhook dispatch, and notifications identical regardless of whether a
bill was created by a human in the portal or an ERP calling this API —
there is exactly one code path for "create a bill," not two that could
drift apart. Verified end to end, live: a customer → account → bill →
control number → payment sequence driven entirely through `curl` against
the real API produced the exact same downstream effects (TZS 50
control-number fee, TZS 50 payment fee, a receipt, `bill.status` flipping
to `paid`) as the same sequence driven through the portal in earlier
phases.

## Authentication — implemented

`apps.api.authentication.ApiKeyAuthentication`:
`Authorization: Bearer <key_id>.<secret>`. `request.tenant` is set
directly from the authenticated `ApiCredential` — the exact same rule as
session-based tenant resolution
(`apps.tenants.middleware.TenantResolutionMiddleware`, see
[MULTI_TENANCY.md](MULTI_TENANCY.md) and
[../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md) ADR-002) —
never from a tenant ID anywhere in the request body or query string.
Verified: a credential from tenant B gets an empty list from
`GET /customers/` when tenant A has customers, and a 404 (not a 403,
which would confirm the row exists) when guessing another tenant's bill
ID.

`ApiCredential` (`apps/api/models.py`) is deliberately **not** a Django
`User` — see ADR-023. Secrets are hashed with Django's own password
hasher (`make_password`/`check_password`, the same primitive protecting
portal login passwords) and shown in full exactly once, at creation or
rotation (`apps.api.credential_services`), in the tenant portal
(`/api-credentials/`, Tenant Administrator only).

## Secret rotation — implemented, simple

`apps.api.credential_services.rotate_credential()` replaces the secret
immediately — the old one stops working the instant rotation completes,
no overlap window. See ADR-024 for why this simpler behavior was chosen
over a grace-period rotation, and what a caller needs to do to rotate
without downtime given that constraint.

## Rate limiting — implemented

`apps.api.throttling.ApiCredentialRateThrottle`, keyed by `key_id` (not
IP — two integrations sharing an egress IP shouldn't throttle each
other). Default `120/min`, configurable via the `API_RATE_LIMIT`
environment variable. Verified: a credential making requests past its
configured rate receives `429`.

## Idempotency — implemented at two layers

1. **Resource-level, via `external_reference`** — `POST /customers/`,
   `/accounts/`, `/bills/` accept an `external_reference` field; a
   repeat call with the same value returns the existing resource (`200`,
   not `201`) unchanged. This is exactly the same idempotency the
   portal-originated services have always had (Phase 2) — the API layer
   doesn't add a new mechanism, it exposes the existing one.
2. **Operation-level, via `Idempotency-Key` header** —
   `POST /payments/` reads this header and passes it straight through
   to `apps.payments.services.initiate_payment`'s `idempotency_key`
   parameter (build spec section 14). A retried payment-initiation
   request with the same header never contacts the provider a second
   time.

## Error envelope

`apps.core.exceptions.drf_exception_handler` (wired since Phase 1) —
every API error returns
`{"error": {"code": ..., "message": ..., "correlation_id": ...}}` with
the appropriate HTTP status. Validation errors from the input
serializers (`apps/api/serializers.py`'s `*CreateSerializer` classes)
flow through DRF's own `ValidationError`, which this handler wraps into
the same envelope.

## OpenAPI schema — implemented

`GET /api/schema/` (raw OpenAPI 3 JSON) and `GET /api/docs/` (interactive
Swagger UI) are both live — `SERVE_INCLUDE_SCHEMA` is `True` as of Phase
6 (it was `False` in Phase 1, since there was nothing to document).
Linked from the tenant portal's API-credentials page.

## What's not built

Fine-grained credential scoping (every `ApiCredential` has full
read/write access to its tenant's data — no "read-only" or
"payments-only" credential type); webhook signature verification for
*inbound* calls to this API (inbound provider callbacks are
signature-verified since Phase 3 — see
[PAYMENT_LIFECYCLE.md](PAYMENT_LIFECYCLE.md) — but nothing calls *into*
`apps/api` with a signed request scheme, since API credentials
themselves are the authentication mechanism here, not request
signing); a real provider selectable via the API (`POST /payments/`
always uses the mock provider, same as the portal, since no real
provider is integrated — see
[PAYMENT_PROVIDER_ARCHITECTURE.md](PAYMENT_PROVIDER_ARCHITECTURE.md)).
