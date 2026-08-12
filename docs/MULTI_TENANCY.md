# Multi-Tenancy

**Status: implemented (Phase 1 foundation).** Code: `apps/tenants/`,
`apps/core/models.py` (`TenantScopedModel`).

## What a tenant is

Any institution or business using KUSANYA — a `Tenant` row
(`apps.tenants.models.Tenant`). Sector (`apps.tenants.models.Sector`) is
informational metadata for reporting/config purposes; it never changes
how the core engine behaves (see
[PRODUCT_REQUIREMENTS.md#universal-data-model](PRODUCT_REQUIREMENTS.md#universal-data-model)).

## The isolation guarantee

Tenant A must never be able to access Tenant B's data. This is enforced,
not just conventionally followed:

1. **Every tenant-owned model inherits `apps.core.models.TenantScopedModel`**,
   which requires a `tenant` foreign key on every such row:
   `apps.organizations.Branch`/`Department` (Phase 1);
   `apps.customers.Customer`/`CustomerAccount`,
   `apps.billing.RevenueSource`/`Bill`/`BillItem`,
   `apps.control_numbers.ControlNumber` (Phase 2); and
   `apps.payments.Payment`/`PaymentAllocation`,
   `apps.webhooks.WebhookEndpoint`/`WebhookDelivery` (Phase 3); and
   `apps.ledger.LedgerEntry`, `apps.revenue.RevenueEvent`,
   `apps.reconciliation.ReconciliationRun`/`ReconciliationException`,
   `apps.settlement.SettlementBatch` (Phase 4). Every future domain model
   follows the same pattern. Note the deliberate exception:
   `apps.providers.PaymentProvider`/`PaymentChannel` are platform-level
   catalog data (which providers KUSANYA integrates with), not tenant
   data, and correctly do *not* inherit `TenantScopedModel` — see
   `apps/providers/models.py`'s module docstring.

2. **`request.tenant` is resolved from membership, not from client
   input.** `apps.tenants.middleware.TenantResolutionMiddleware` looks up
   the authenticated user's active `TenantMembership` for the tenant
   recorded in their session, re-validating on every request. A forged or
   stale `active_tenant_id` session value for a tenant the user isn't an
   active member of resolves to **no tenant**, never to that tenant's
   data. See [../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md)
   ADR-002, and the enforcement test
   `apps/tenants/tests/tests.py::TestTenantIsolationAcrossPortal`.

3. **The same "never trust client-supplied tenant identity" rule extends
   to non-session contexts.** `apps.payments.views.mock_provider_callback`
   (Phase 3) has no session and no `request.tenant` at all — it's called
   by a payment provider, not a logged-in user. Tenant is instead derived
   by looking up the `Payment` row matching the callback's (signature-
   verified) `provider_reference`, never accepted as a field in the
   callback payload itself. The same principle, a different mechanism —
   see [PAYMENT_LIFECYCLE.md](PAYMENT_LIFECYCLE.md).

4. **Server-side authorization, not template-only checks.**
   `apps.tenants.permissions.require_tenant_role` / `require_platform_role`
   raise `PermissionDenied` (HTTP 403) before a view runs; templates use
   the resolved role only to decide what to *show*, never as the actual
   access boundary (build spec section 8).

5. **API-key-based tenant resolution (Phase 6) follows the identical
   rule via a third mechanism.** `apps.api.authentication.ApiKeyAuthentication`
   sets `request.tenant` directly from the authenticated `ApiCredential`
   — never from a tenant ID anywhere in the request body or query
   string, for any `/api/v1/` endpoint. Verified:
   `TestTenantIsolationViaApi` — a credential from tenant B gets an
   empty list from `GET /customers/` when tenant A has customers, and a
   `404` (not a `403`, which would leak that the row exists) when
   guessing another tenant's bill ID. Three independent tenant-resolution
   mechanisms now exist (session, provider-callback-via-payment-lookup,
   API credential) and all three obey the same rule — see
   [../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md) ADR-002.

## What's not built yet

Row-level tenant filtering at the queryset layer (e.g. a manager that
automatically scopes `Model.objects` to `request.tenant`) is still not
implemented — every portal *and API* view across Phases 2–6
(`apps.customers.views`, `apps.billing.views`,
`apps.control_numbers.views`, `apps.payments.views`,
`apps.webhooks.views`, `apps.ledger.views`, `apps.revenue.views`,
`apps.reconciliation.views`, `apps.settlement.views`, `apps.api.views`)
filters explicitly with `.filter(tenant=request.tenant)`/
`get_object_or_404(..., tenant=request.tenant)` rather than an automatic
manager. This is directly what the tenant-isolation tests across those
apps exercise (e.g. `TestBillPortalTenantIsolation`,
`TestTenantIsolationViaApi`: a guessed URL for another tenant's bill
404s, another tenant's bill never appears in your bill list). An
automatic tenant-scoping manager would reduce the chance of a future
view forgetting this filter — now that all six phases are built and the
explicit-filter pattern has held up correctly across every one of them,
this is worth introducing before any Phase 7 hardening work, as a
refactor with the existing tests as its safety net, rather than each app
continuing to repeat the same explicit filter by convention. Settlement's
platform-only views (`generate_batch`, `mark_completed`) remain the one
deliberate exception — they operate across tenants by design (a platform
admin chooses which tenant to settle), gated by `require_platform_role`
instead of tenant-membership.

## Tenant lifecycle

`PENDING` (registered, awaiting platform approval) → `ACTIVE` (approved,
usable) → `SUSPENDED` / `REJECTED`. See `apps.tenants.views.onboard` and
`approve_tenant` for Journey A (build spec section 47).
