# Testing

## Running the suite

```bash
python -m pytest            # all tests
python -m pytest -v         # verbose
python -m pytest apps/tenants  # one app
```

Uses `pytest` + `pytest-django` (`pytest.ini` sets
`DJANGO_SETTINGS_MODULE=config.settings.testing`). Tests run against a
real PostgreSQL database — Django creates and tears down a disposable
`test_<name>` database automatically; there is no SQLite fallback (the
platform's actual behavior around constraints, `Decimal` precision, and
concurrent-transaction semantics should be verified against the same
engine production uses, not a different one that happens to be
convenient for tests).

`config/settings/testing.py` additionally: uses `MD5PasswordHasher`
(speed, not security, since test passwords aren't real secrets),
`CELERY_TASK_ALWAYS_EAGER=True` (so Celery tasks execute synchronously
and their effects are directly assertable), locmem cache, and locmem
email backend.

## What's covered today (Phase 1 + 2 — 52 tests)

- **Health check** — `apps/core/tests/tests.py`: DB/cache connectivity,
  correlation ID generation and echo.
- **Tenant isolation** — `apps/tenants/tests/tests.py`: a forged/stale
  session `active_tenant_id` for a tenant the user has no active
  membership in resolves to no tenant, never to that tenant's data
  (`TestTenantResolutionMiddleware`, `TestTenantIsolationAcrossPortal`) —
  this is the platform's single most important test class.
- **RBAC** — `TestRBACPermissions`: platform-role and tenant-role checks,
  `require_tenant_role`/`require_platform_role` decorator behavior,
  superuser bypass.
- **Tenant onboarding** — `TestTenantOnboarding`: registration creates a
  `PENDING` tenant + admin membership; approval requires the correct
  platform role (403 without it); approved tenant transitions to
  `ACTIVE`.
- **Audit log** — `apps/audit/tests/tests.py`: hash-chain linkage from
  genesis, chain verification, immutability (`save()`/`delete()` on an
  existing record both raise), login/login-failure auto-audit via
  Django's auth signals.
- **User model** — `apps/users/tests/tests.py`: no `username` DB field,
  email normalization, unique email constraint, superuser flag
  correctness, password hashing.
- **Organizations** — per-tenant uniqueness of `Branch` names, and that
  the same name is allowed across different tenants (a direct,
  minimal tenant-isolation check at the data layer).
- **Customers** (`apps/customers/tests/tests.py`) — idempotent creation
  by `external_reference` for both `Customer` and `CustomerAccount`;
  blank references never falsely deduplicate two different walk-in
  customers; the same `external_reference` is allowed to exist
  independently for two different tenants.
- **Billing** (`apps/billing/tests/tests.py`) — idempotent bill creation
  (a repeat call with the same `external_reference` returns the original
  bill *unchanged*, even if the retried call's line items differ); the
  status state machine (`DRAFT → ACTIVE` allowed, `DRAFT → PAID` rejected,
  `CANCELLED` is terminal); portal-level tenant isolation for bills
  (guessing another tenant's bill URL 404s; another tenant's bill never
  appears in your bill list).
- **Control numbers** (`apps/control_numbers/tests/tests.py`) — the core
  pricing-model guarantee, directly: one creation followed by two more
  requests for the same bill creates exactly one `ControlNumber` row and
  reports `created=True` only the first time (mirrors build spec section
  3's worked example); the `bill` `OneToOneField` rejects a second
  control number for the same bill at the database level; a persistent
  control number can be reissued after its predecessor is cancelled;
  generated values never contain the customer's name or phone number.

**Also verified manually, end-to-end over real HTTP** during Phase 2
development (login → dashboard → create customer → create account →
create bill → bill auto-requests a control number → explicitly
re-requesting it returns the identical value, confirmed against both the
rendered page and the database) — this is not part of the automated
suite, but the same guarantee the automated tests check was independently
confirmed through the actual portal, not just at the service-function
level.

## Critical scenarios not yet testable (blocked on later phases)

Everything from build spec section 34 that depends on payments —
control-number-creation-fee-charged-once (Phase 4's revenue engine reading
the `created`/`reused` distinction Phase 2 already provides), duplicate
webhook → no second payment, partial/full payment, provider timeout →
`UNKNOWN`, reconciliation, reversal, refund, API rate limiting, webhook
signature validation — cannot be tested because the code they'd test
doesn't exist yet (Phase 3–6). Each of those phases' documentation
([PRICING_MODEL.md](PRICING_MODEL.md), [PAYMENT_LIFECYCLE.md](PAYMENT_LIFECYCLE.md))
lists the specific tests that phase must ship with.

## Fixtures

`conftest.py` at the project root: `make_user`, `make_tenant`,
`make_membership`, `make_platform_role` — factory fixtures used across
every app's test module so tenant/user/membership setup isn't duplicated
per test file.
