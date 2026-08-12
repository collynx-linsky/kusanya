# RBAC — Role-Based Access Control

**Status: implemented (Phase 1 foundation).** Code:
`apps/users/models.py` (`PlatformRole`, `PlatformMembership`),
`apps/tenants/models.py` (`TenantRole`, `TenantMembership`),
`apps/tenants/permissions.py` (enforcement).

## Two independent role vocabularies

**Platform-level** (`apps.users.models.PlatformRole`) — roles at KUSANYA
the company: Platform Super Administrator, Platform Finance
Administrator, Platform Operations Administrator, Platform Compliance
Administrator, Platform Support Administrator, Platform Auditor.

**Tenant-level** (`apps.tenants.models.TenantRole`) — roles within one
institution: Tenant Administrator, Finance Manager, Accountant, Billing
Officer, Reconciliation Officer, Viewer, API Client.

A user can hold platform roles, tenant roles (in one or more tenants,
potentially different roles in each), both, or neither. See
[../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md) ADR-004 for
why these are separate models rather than one polymorphic table.

## Enforcement

Both are enforced server-side via decorators in
`apps.tenants.permissions`:

```python
@require_platform_role(PlatformRole.SUPER_ADMIN, PlatformRole.OPERATIONS_ADMIN)
def approve_tenant(request, pk): ...

@require_tenant_role(TenantRole.FINANCE_MANAGER)
def some_tenant_finance_view(request): ...
```

Both raise `django.core.exceptions.PermissionDenied` (→ HTTP 403,
rendered via `templates/403.html`) when the check fails. `is_superuser`
implicitly satisfies any platform-role check
(`has_platform_role`) — a Django superuser can always act, matching
Django's own convention for its `is_superuser` flag.

**Templates are not the access-control boundary.** `current_tenant` /
`current_tenant_membership` are available in every template (via
`apps.tenants.context_processors.current_tenant`) purely to decide what
to *render* — e.g. hiding the "Admin" nav link from non-staff users. The
actual authorization decision is always re-checked server-side in the
view, per build spec section 8's explicit warning against
template-only permission checks.

## Django admin site access vs. `PlatformMembership`

`User.is_staff`/`is_superuser` (Django's built-ins) currently gate
`/admin/` and the platform-dashboard route (`apps.core.views.platform_dashboard`).
`PlatformMembership` roles are enforced independently wherever
`require_platform_role` is used (e.g. tenant approval) — the two
mechanisms are deliberately not merged (see ADR-004): being `is_staff`
does not imply holding any specific `PlatformRole`, and a future
non-Django-admin platform portal could grant `PlatformRole`s to users who
never need raw Django admin access at all.

## What's not built yet

MFA (build spec calls for "MFA-ready architecture" — no MFA enforcement
exists yet; Django's session/auth stack does not preclude adding it, but
nothing in Phase 1 requires a second factor). Fine-grained *object-level*
permissions beyond tenant scoping (e.g. "this Accountant can only see
Branch X's bills") are not modeled — `TenantMembership` grants a role
across the whole tenant, not per-branch, in Phase 1.
