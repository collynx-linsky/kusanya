# Database Architecture

**Status: implemented (Phase 1 foundation), extended per phase.**

## Engine

PostgreSQL only — no SQLite fallback anywhere, including tests (see
[TESTING.md](TESTING.md)). `psycopg[binary]` (psycopg 3) is the driver.
Configured via `DATABASE_URL` (django-environ) in
`config/settings/base.py`; `ATOMIC_REQUESTS = True` — every request
that writes is wrapped in a transaction by default.

## Conventions every model follows

- **UUID primary keys** for all KUSANYA domain models
  (`apps.core.models.BaseModel`) — see
  [../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md) ADR-001.
  Django's own internal apps (auth, contenttypes, sessions,
  django_celery_beat) keep their native integer PKs — not worth fighting
  third-party migrations to change.
- **`created_at`/`updated_at`** on every model via `BaseModel`.
- **Money is always `Decimal`/`DecimalField`, never `float`** — see
  ADR-003 and `apps.core.money`. `money_field_kwargs()` standardizes
  `max_digits=18, decimal_places=2` so every future model's amount field
  is consistent without each app re-deciding precision.
- **UTC internally.** `USE_TZ = True`, `TIME_ZONE = "UTC"` — all
  timestamps stored in UTC; local-time rendering is a template/view
  concern, never a storage concern.
- **Explicit currency fields.** Any model that stores an amount also
  stores its currency code (`Tenant.default_currency` today; every
  Phase 2+ money-bearing model will follow the same pattern) — see
  [MONEY_FLOW.md](MONEY_FLOW.md).
- **DB-level constraints, not just application checks.** E.g.
  `TenantMembership` has a `UniqueConstraint(tenant, user)`,
  `PlatformMembership` has `UniqueConstraint(user, role)`, `Branch`/
  `Department` have per-tenant unique-name constraints — enforced by
  Postgres, not just Django form validation, so a bug elsewhere in the
  code can't silently create duplicate rows. Phase 2 extends this with
  **conditional unique constraints** (`UniqueConstraint(..., condition=Q(...))`)
  where uniqueness only applies to a subset of rows — e.g.
  `Customer`/`CustomerAccount`/`Bill` only enforce uniqueness on
  `external_reference` when it's non-blank (so many blank references
  don't collide), and `ControlNumber` only enforces "at most one per
  account" among `status="active"` rows (so historical
  expired/cancelled ones don't block reissuing) — see
  [../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md) ADR-011.
  Phase 3 extends the same pattern to `Payment.idempotency_key` (unique
  per tenant, only when non-blank) and — most importantly —
  `PaymentCallbackEvent(provider, external_event_id)` (unique, only when
  non-blank), which is what makes "the same provider webhook delivered
  three times produces one financial event" a database-enforced fact
  rather than a hope — see ADR-014.
- **Tenant-scoped models inherit `TenantScopedModel`**, which adds a
  required `tenant` FK with `on_delete=PROTECT` — a tenant can't be
  deleted out from under data that still references it.

## Migrations

Standard Django migrations only; production databases are never
hand-edited (build spec section 40). `python manage.py makemigrations` /
`migrate` — see [README.md](../README.md) for the exact commands.

## What's not built yet

Financial-record immutability at the ledger level (Phase 4 —
`LedgerEntry` will follow the same "block UPDATE/DELETE at the model
layer" pattern already implemented for `AuditLog`, see
[LEDGER_SPEC.md](LEDGER_SPEC.md)). Database-role-level permission
restriction (the app's Postgres role currently has full DML rights on
every table, including `audit_auditlog` — see
[../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md) ADR-006 for
why that matters and is tracked as a pre-production follow-up).
