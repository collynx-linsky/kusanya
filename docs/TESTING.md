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

## What's covered today (Phase 1 + 2 + 3 + 4 + 5 + 6 — 149 tests)

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

- **Providers** (`apps/providers/tests/tests.py`) — the mock adapter's
  outcome simulation (successful/failed/pending/timeout), the honesty
  property that a simulated timeout still deterministically records what
  "actually happened" server-side (queryable afterward), reference
  validation, and callback signature verification (correct signature
  accepted, tampered payload rejected, missing signature rejected).
- **Payments** (`apps/payments/tests/tests.py`, 22 tests) — the full
  lifecycle: successful/failed/partial/multi-payment scenarios and their
  effect (or lack of effect) on the underlying bill; the UNKNOWN-on-
  timeout rule and its resolution via `query_payment()` (including that
  querying twice doesn't double-allocate); initiation idempotency by
  `idempotency_key`; **the three-times-duplicate-webhook guarantee**
  (`test_same_event_delivered_three_times_produces_one_financial_event`
  — exactly one `PaymentAllocation` and one paid bill after three
  identical callback deliveries); unmatched and invalid-signature
  callback handling; refund/reversal, including that a payment which
  never succeeded cannot be refunded.
- **Webhooks** (`apps/webhooks/tests/tests.py`) — signature
  build/verify correctness (including tamper detection and
  order-independent canonical JSON); `dispatch_event` creates exactly one
  delivery per active, subscribed, *same-tenant* endpoint; delivery
  execution success/non-2xx/network-error handling; exhausting
  `max_attempts` moves a delivery to `DEAD_LETTER`.
- **Ledger** (`apps/ledger/tests/tests.py`) — `.save()`/`.delete()` on an
  existing entry both raise; a correction posts a new, linked
  compensating entry while the original is provably untouched.
- **Revenue** (`apps/revenue/tests/tests.py`) — **the build spec's own
  worked example, verbatim**
  (`TestBuildSpecWorkedExample::test_one_control_number_five_payments_equals_300`):
  one control-number creation + five successful payments totals exactly
  TZS 300, split correctly into TZS 50 (creation) + TZS 250 (5×TZS 50
  payments); creation charges the fee exactly once across three requests,
  with the reused requests posting TZS 0 and no ledger entry; failed
  payments and duplicate callbacks charge nothing; both reversal/refund
  accounting-treatment policies (`CLAWBACK`/`RETAIN`) produce the correct
  compensating event without ever deleting the original; `RevenueEvent`
  immutability.
- **Reconciliation** (`apps/reconciliation/tests/tests.py`) — a run
  resolves a stale `UNKNOWN` payment via the same `query_payment()` path
  Phase 3 already tests; a payment stuck `UNKNOWN` with no provider
  record stays `UNKNOWN` and opens a `STUCK_UNKNOWN` exception; **drift
  detection**: a payment's provider-side record is deliberately altered
  after the fact, and reconciliation flags a `STATUS_MISMATCH` exception
  *without* changing the already-settled `Payment.status`; a clean match
  is counted, not flagged; exception resolution records who/when/why.
- **Settlement** (`apps/settlement/tests/tests.py`) — a batch correctly
  aggregates successful payments' gross amount, platform fees (via
  `RevenueEvent`), and computes net; failed/pending payments are
  excluded; **a payment is never settled twice** — generating a batch
  for the same period a second time includes zero payments, because the
  first batch already claimed them; marking a batch completed records
  the external reference and dispatches a `settlement.completed`
  webhook.
- **Notifications** (`apps/notifications/tests/tests.py`) — default
  template variable substitution; a missing variable renders blank, never
  `KeyError`; a tenant's `NotificationTemplate` override takes precedence
  over the default, an inactive override is ignored; `send_notification`
  creates exactly one `Notification` per channel with a usable recipient
  and skips channels with none; email delivery lands in
  `pytest-django`'s `mailoutbox`; the mock SMS channel marks a
  notification `sent` without a real gateway; an unimplemented channel
  (WhatsApp/push) fails loudly with a clear error, never silently; and
  **integration tests wired through real domain events** — creating a
  bill/control number sends the right notification, reusing a control
  number sends no second one, a full payment sends `bill_fully_paid` (not
  generic `payment_successful`), a partial payment sends `payment_partial`.
- **Receipts** (`apps/receipts/tests/tests.py`) — a receipt is generated
  automatically on a successful payment and *only* then (no receipt for a
  failed payment; `generate_receipt()` raises `ValidationError` for any
  non-`SUCCESSFUL` payment); calling it twice returns the same receipt,
  never a duplicate; the snapshotted `remaining_balance_at_issue` matches
  the bill's actual balance at that moment.
- **Reports** (`apps/reports/tests/tests.py`) — the bills report's status
  filter excludes non-matching bills; CSV export returns real
  `text/csv` content; the outstanding-balances report excludes bills with
  zero balance; the collections report's totals reflect only
  `SUCCESSFUL` payments.

- **API** (`apps/api/tests/tests.py`, 18 tests) — credential creation
  returns the raw secret exactly once while only a hash is ever stored;
  rotation invalidates the old secret and activates the new one;
  revocation is enforced; authentication rejects missing/wrong/revoked
  credentials and credentials belonging to a non-`ACTIVE` tenant;
  **tenant isolation over the API specifically** — a credential from
  tenant B gets an empty customer list when tenant A has customers, and
  a `404` (not `403`) guessing another tenant's bill ID; **API-level
  idempotency** — creating the same customer/bill twice by
  `external_reference` returns the same resource unchanged, requesting a
  control number twice returns the same value, and a repeated
  `POST /payments/` with the same `Idempotency-Key` header returns the
  same payment; **rate limiting** — a credential's requests past its
  configured throttle rate receive `429`; the OpenAPI schema and docs
  endpoints are served; and a full
  customer→account→bill→control-number→payment sequence driven entirely
  through the Django test client's HTTP interface (not direct service
  calls) ends with the bill `paid` and balance `0.00`.

**Also verified manually, end-to-end over real infrastructure**, outside
the automated suite:

- **Phase 2** — the control-number reuse guarantee, driven entirely over
  real HTTP with real login/CSRF/RBAC: register → approve → log in →
  create customer → create account → create bill (auto-issues a control
  number) → explicitly re-request it → identical value returned,
  confirmed against both the rendered page and the database.
- **Phase 3** — the full payment → webhook pipeline with a real Celery
  worker (not `CELERY_TASK_ALWAYS_EAGER`): initiating a successful mock
  payment produced `bill.created` and `payment.successful` webhook
  deliveries to a local HTTP receiver, each with a correctly verifiable
  HMAC signature (independently re-checked afterward against the
  endpoint's stored secret, including confirming a tampered body fails
  verification) and each recorded `DELIVERED` with HTTP 200 after exactly
  one attempt.
- **Phase 4** — the entire ledger/revenue/reconciliation/settlement
  pipeline in one live run against real PostgreSQL: one control number +
  five successful payments produced exactly TZS 300 total platform
  revenue (matching the build spec's worked example to the cent) and a
  full, correctly itemized ledger (`payment_received`,
  `institution_entitlement`, `platform_payment_fee`,
  `platform_control_number_fee` — every entry separately identifiable,
  per [MONEY_FLOW.md](MONEY_FLOW.md)); a settlement batch generated from
  those five payments computed gross/platform-fee/net correctly, a
  second generation attempt for the same period correctly claimed zero
  payments, and `run_reconciliation()` matched all five payments against
  the provider with zero exceptions.
- **Phase 5** — a full bill → control-number → payment → receipt flow
  against real PostgreSQL, real Redis, and a real Celery worker: the flow
  produced six notifications (`bill_created`, `control_number_generated`,
  `bill_fully_paid`, each on both email and SMS) and one receipt; after a
  worker was confirmed running (a stale worker process from an earlier
  session had been silently swallowing tasks with a `NotRegistered`
  error — caught and fixed by clearing it), all six notifications reached
  `status=sent` with real timestamps.
- **Phase 6** — a real `ApiCredential`, created through the tenant
  portal, drove a full `curl` sequence against the live server:
  `GET /institutions/me/` → `POST /customers/` → `/accounts/` →
  `/bills/` (with a retried, unmodified-by-the-retry idempotency check)
  → `/bills/{id}/control-number/` → `/payments/` (with an
  `Idempotency-Key` header) — ending with the bill `paid`, a TZS 50
  control-number fee and TZS 50 payment fee both posted to
  `RevenueEvent`, a receipt generated, and unauthenticated/malformed
  requests to the same endpoints correctly rejected with `401`.

## Critical scenarios — all 20 covered

Every one of build spec section 34's 20 critical scenarios now has
either an automated test or documented live verification: control number
creation/reuse/fee-charged-exactly-once, successful/partial/full/failed
payment, provider timeout → UNKNOWN, duplicate webhook → no second
payment, reconciliation, reversal, refund, tenant isolation (across the
portal *and*, as of Phase 6, the API independently), unauthorized API
access (`401`), API rate limiting (`429`), and invalid webhook signature
handling (tested for the *provider→KUSANYA* direction since Phase 3; the
*ERP→KUSANYA* direction uses credential authentication rather than
request signing — see [API_ARCHITECTURE.md](API_ARCHITECTURE.md) for why
that's the correct mechanism for this layer, not a gap relative to the
scenario's intent).

## Fixtures

`conftest.py` at the project root: `make_user`, `make_tenant`,
`make_membership`, `make_platform_role`, `make_customer`,
`make_customer_account`, `mock_provider` (the seeded `PaymentProvider`
row), and `make_bill_with_control_number` (the full tenant → customer →
account → bill → control number chain in one call) — factory fixtures
used across every app's test module so this setup isn't duplicated per
test file.
