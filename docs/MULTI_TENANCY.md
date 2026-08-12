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
   `apps.organizations.Branch`/`Department` (Phase 1), and
   `apps.customers.Customer`/`CustomerAccount`,
   `apps.billing.RevenueSource`/`Bill`/`BillItem`,
   `apps.control_numbers.ControlNumber` (Phase 2). Every future domain
   model follows the same pattern.

2. **`request.tenant` is resolved from membership, not from client
   input.** `apps.tenants.middleware.TenantResolutionMiddleware` looks up
   the authenticated user's active `TenantMembership` for the tenant
   recorded in their session, re-validating on every request. A forged or
   stale `active_tenant_id` session value for a tenant the user isn't an
   active member of resolves to **no tenant**, never to that tenant's
   data. See [../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md)
   ADR-002, and the enforcement test
   `apps/tenants/tests/tests.py::TestTenantIsolationAcrossPortal`.

3. **Server-side authorization, not template-only checks.**
   `apps.tenants.permissions.require_tenant_role` / `require_platform_role`
   raise `PermissionDenied` (HTTP 403) before a view runs; templates use
   the resolved role only to decide what to *show*, never as the actual
   access boundary (build spec section 8).

## What's not built yet

API-key-based tenant resolution for external ERP/POS integrations (Phase
6) — it will follow the identical rule (derive tenant from the
authenticated credential, never trust a client-supplied tenant ID), just
via an API key/secret instead of a session. Row-level tenant filtering at
the queryset layer (e.g. a manager that automatically scopes
`Model.objects` to `request.tenant`) is still not implemented — Phase 2's
views (`apps.customers.views`, `apps.billing.views`,
`apps.control_numbers.views`) each filter explicitly with
`.filter(tenant=request.tenant)`/`get_object_or_404(..., tenant=request.tenant)`
rather than an automatic manager, and this is directly what the Phase 2
tenant-isolation tests exercise (`TestBillPortalTenantIsolation`: a
guessed URL for another tenant's bill 404s, another tenant's bill never
appears in your bill list). An automatic tenant-scoping manager would
reduce the chance of a future view forgetting this filter — worth
introducing before Phase 3 adds more tenant-scoped views, rather than
each app continuing to repeat the same explicit filter by convention.

## Tenant lifecycle

`PENDING` (registered, awaiting platform approval) → `ACTIVE` (approved,
usable) → `SUSPENDED` / `REJECTED`. See `apps.tenants.views.onboard` and
`approve_tenant` for Journey A (build spec section 47).
