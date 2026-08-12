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

## What's covered today (Phase 1 — 30 tests)

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

## Critical scenarios not yet testable (blocked on later phases)

Everything from build spec section 34 that depends on billing/payments —
control-number creation-fee-charged-once, duplicate webhook →
no second payment, partial/full payment, provider timeout → `UNKNOWN`,
reconciliation, reversal, refund, API rate limiting, webhook signature
validation — cannot be tested because the code they'd test doesn't exist
yet (Phase 2–6). Each of those phases' documentation
([PRICING_MODEL.md](PRICING_MODEL.md), [PAYMENT_LIFECYCLE.md](PAYMENT_LIFECYCLE.md))
lists the specific tests that phase must ship with.

## Fixtures

`conftest.py` at the project root: `make_user`, `make_tenant`,
`make_membership`, `make_platform_role` — factory fixtures used across
every app's test module so tenant/user/membership setup isn't duplicated
per test file.
