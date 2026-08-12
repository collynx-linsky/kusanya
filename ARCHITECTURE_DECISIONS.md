# Architecture Decisions

Major architectural decisions, recorded as they're made. Each entry: the
decision, why, what else was considered, and the consequences. This file
grows over time — it is not rewritten to look tidy in hindsight.

---

## ADR-001: UUID primary keys platform-wide

**Decision:** Every domain model's primary key is a `UUIDField`
(`apps.core.models.BaseModel`), not an auto-incrementing integer.

**Reason:** KUSANYA identifiers are exposed externally from day one —
control numbers, payment references, webhook payloads, receipts, ERP
integrations. A sequential integer ID leaks operational volume (a
competitor watching bill IDs tick up learns your transaction rate) and
invites enumeration attacks against API endpoints.

**Alternatives considered:** Integer PKs with a separate public UUID
field. Rejected — doubles the indexing cost and creates two identifiers
per row to keep straight for no real benefit once UUID is the PK anyway.

**Consequences:** Slightly larger indexes than `BigAutoField`; UUIDv4 is
not naturally sortable by creation time (mitigated by keeping explicit
`created_at` on every model). `DEFAULT_AUTO_FIELD` remains `BigAutoField`
for Django's own internal tables (django_celery_beat, contenttypes, etc.)
— only KUSANYA domain models opt into UUID via `BaseModel`.

---

## ADR-002: Tenant resolved from membership, never from a client-supplied ID

**Decision:** `apps.tenants.middleware.TenantResolutionMiddleware` sets
`request.tenant` by looking up the authenticated user's active
`TenantMembership`, re-validated on every request. A session key records
which tenant was last selected, but it is only ever a hint re-checked
against real membership rows — never trusted directly.

**Reason:** Section 7 of the build spec is unambiguous: tenant isolation
is critical, and tenant IDs supplied by the client must never be trusted.
Deriving `request.tenant` from the authenticated identity's actual
membership, every request, is the only way to make cross-tenant access a
structurally hard bug to introduce rather than a "please remember to
filter by tenant" convention.

**Alternatives considered:** Trusting a `tenant_id` URL parameter/header
validated once per session at login. Rejected — a stale or forged session
value would then grant standing access until the session expires, and any
one view that forgets to re-check becomes a tenant-isolation breach.

**Consequences:** One extra query per authenticated request. Every
tenant-scoped view must use `request.tenant`, never a value pulled from
`request.GET`/`POST`/route kwargs — this is enforced by convention today
(see `apps.tenants.permissions.require_tenant_role`) and should graduate
to an automated check (e.g. a lint rule or test that greps for
`Tenant.objects.get(id=request` patterns) before Phase 2 adds tenant-owned
financial data.

---

## ADR-003: Money as `Decimal`/`DecimalField`, currency always explicit

**Decision:** No monetary value is ever a Python `float` or a SQL
floating-point column. `apps.core.money` centralizes currency exponents
and a `money_field_kwargs()` helper so every future model's amount field
is `DecimalField(max_digits=18, decimal_places=2)` by construction, not by
each app remembering to configure it correctly.

**Reason:** Build spec section 30/31, and it's simply correct — floating
point cannot represent currency amounts exactly, and silent rounding
errors in a payments platform are a direct financial/legal liability.

**Consequences:** All arithmetic on money must go through `Decimal`
(never mix with `float`); JSON API responses will serialize amounts as
strings, not native JSON numbers, once the API exists (Phase 6) to avoid
client-side float coercion.

---

## ADR-004: Custom `User` model is email-only, platform roles are separate from tenant roles

**Decision:** `apps.users.User` extends `AbstractUser` with `username =
None`, `email` as `USERNAME_FIELD`. Platform-level RBAC
(`apps.users.PlatformMembership`) and tenant-level RBAC
(`apps.tenants.TenantMembership`) are two independent tables — a user's
platform roles say nothing about their tenant roles and vice versa.

**Reason:** Institutions register with an email, not a username (build
spec section 47, Journey A). Keeping platform and tenant RBAC as separate
models (rather than one polymorphic "role" table) matches the build
spec's explicit split between platform-level roles (section 8, "Platform
Super Administrator" etc.) and tenant-level roles ("Tenant Administrator"
etc.) — they have different meaning, different lifecycles, and are
managed by different people.

**Alternatives considered:** A single `Membership` model with a nullable
`tenant` FK (null = platform-level). Rejected for Phase 1 — it makes every
query need to remember to filter on tenant-null-ness correctly, and the
two role vocabularies (`PlatformRole` vs `TenantRole`) don't overlap
anyway.

**Consequences:** `User.is_staff`/`is_superuser` (Django's built-in flags)
currently gate the Django admin and the platform-dashboard route; the
richer `PlatformMembership` roles exist and are enforced by
`apps.tenants.permissions.require_platform_role` but nothing in Phase 1's
UI yet exposes fine-grained differences between e.g. Finance Admin and
Compliance Admin — that authorization granularity is available for Phase
2+ views to use as those views are built.

---

## ADR-005: Django apps organized one-per-domain, Phase 1 ships only the foundation apps

**Decision:** `apps/` contains one Django app per bounded domain concept
(`core`, `users`, `accounts`, `tenants`, `organizations`, `audit` in Phase
1). Domain apps for billing, control numbers, payments, providers, ledger,
reconciliation, settlement, revenue, notifications, webhooks, api, and
reports are **not** scaffolded yet.

**Reason:** Build spec section 24 ("do not create one giant app") and
section 42 ("work in phases... do not attempt to write every feature in
one giant uncontrolled generation"). An empty `apps/billing/` with no
models is not "foundation," it's an unused placeholder that would need to
be re-learned when Phase 2 actually starts.

**Consequences:** `INSTALLED_APPS` in `config/settings/base.py` will grow
app-by-app as each phase begins; this is intentional and each addition
should be a reviewable, scoped change rather than a silent expansion of an
already-registered-but-empty app.

---

## ADR-006: Audit log is hash-chained but explicitly not a cryptographic tamper-proof guarantee

**Decision:** `apps.audit.AuditLog` computes a SHA-256 hash over each
record chained to the previous record's hash, and blocks `save()` on
existing rows and all `delete()` calls at the model layer.

**Reason:** Build spec section 29 requires audit logs to be
"tamper-resistant." A hash chain makes accidental or unsophisticated
tampering (an UPDATE/DELETE run against the table) immediately detectable
via `AuditLog.verify_chain()`.

**What this does NOT claim:** a DB user with UPDATE rights on the
`audit_auditlog` table could rewrite history and recompute a
self-consistent chain from that point forward. Real tamper-evidence needs
the application's DB role to lack UPDATE/DELETE grants on that table (DB
permission enforcement), plus off-box log shipping and/or periodic
external anchoring. None of that is implemented in Phase 1 — see
`apps/audit/models.py`'s module docstring and
`docs/SECURITY_ARCHITECTURE.md`. Overstating this guarantee would violate
the "no invented security properties" principle as much as skipping audit
logging entirely.

**Consequences:** A follow-up task before production: lock down the
Postgres role Django connects as to INSERT/SELECT-only on `audit_auditlog`
(via a migration-time `GRANT`/`REVOKE`, since Django's ORM has no native
concept of per-table DB permissions), and decide on an external log sink.

---

## ADR-007: Settings split by environment, not by a single `DEBUG` flag

**Decision:** `config/settings/{base,development,testing,production}.py`,
selected via `DJANGO_SETTINGS_MODULE`, instead of one `settings.py` with
`if DEBUG:` branches.

**Reason:** Production-only requirements (SECRET_KEY has no insecure
default, ALLOWED_HOSTS has no default, HSTS/SSL redirect on) need to be
impossible to accidentally leave off, not just conditionally applied.
Making `production.py` `raise RuntimeError` on a missing/default
`SECRET_KEY` fails a bad deploy at process start, not at the first request
that happens to expose the problem.

**Consequences:** Three settings modules to keep roughly in sync;
`base.py` is the single source of truth for everything that should be
identical across environments, so drift is opt-in per environment file,
not the default.

---

## ADR-008: Server-rendered UI (Django templates + Bootstrap 5 + HTMX), not a JS SPA framework

**Decision:** No React/Next.js/Vue for the web application (build spec
section 25).

**Reason:** Explicit build-spec requirement, and it matches the actual
need — this is a financial-dashboard/forms-heavy admin application, not a
highly interactive consumer product. HTMX covers the interactivity that
matters (partial page updates, live status polling for payment states in
later phases) without a separate frontend build pipeline or API
duplication between "the API the ERP integrations use" and "the API the
SPA uses."

**Consequences:** Bootstrap/HTMX are currently loaded from CDN
(`templates/base.html`) for development speed; production deployment
should vendor these assets locally (see docs/DEPLOYMENT.md) so the app
doesn't have a runtime dependency on a third-party CDN's availability.

---

## ADR-009: Python 3.14 locally, Python 3.12 in the Docker image

**Decision:** The Dockerfile pins `python:3.12-slim`; local development on
this machine happens to run Python 3.14.5 (the only interpreter installed
on the host at project start).

**Reason:** All dependencies (Django 5.2, psycopg 3.3, Celery 5.6, etc.)
installed and passed the full test suite cleanly on 3.14 during Phase 1
(see the development report), so there's no correctness reason to avoid
it locally. The Docker image pins 3.12 as the more conservative,
widely-deployed choice for anything resembling a production target,
rather than following the host machine's incidental interpreter version.

**Consequences:** Contributors on other machines should not assume 3.14
is required — the `requirements/*.txt` floors (`Django>=5.1,<6.0` etc.)
are chosen to work on 3.12–3.14. If a future dependency drops 3.12
support before this decision is revisited, bump the Docker image, not the
requirement floors.

---

## ADR-010: Idempotency via `get_or_create_*()` + DB constraint + `IntegrityError` recovery, not check-then-create

**Decision:** Every idempotent creation path in Phase 2
(`apps.customers.services.get_or_create_customer`/`_account`,
`apps.billing.services.get_or_create_bill`,
`apps.control_numbers.services.get_or_create_for_bill`/`_for_account`)
follows the same three-part pattern: (1) query for an existing row
matching the idempotency key, return it if found; (2) if not found,
attempt to create inside `transaction.atomic()`; (3) if creation raises
`IntegrityError` (a concurrent request won the race), re-query for the
row that request just created and return it — never treat that
`IntegrityError` as a genuine failure.

**Reason:** A plain "check, then create" (steps 1–2 only) has a race
window: two concurrent requests for the same new bill can both pass step
1's check before either commits step 2, producing two bills for what
should have been one idempotent operation. Build spec section 14 requires
idempotency to actually hold under concurrency (this is exactly the
scenario a retried ERP webhook or a double-clicked "create bill" button
produces), not just in the common non-concurrent case. The database
constraint (a `UniqueConstraint` on the idempotency key, or — for
control numbers bound to a bill — the `bill` field's own
`OneToOneField`) is the actual source of truth that makes the race safe;
the `IntegrityError`-catch-and-re-fetch is just how the losing request
finds out what the winner created instead of surfacing a 500.

**Alternatives considered:** A `SELECT ... FOR UPDATE` lock on some
parent row before the check. Rejected for Phase 2 — it requires
identifying and locking the right parent row per idempotency scope
(straightforward for "one control number per bill," less obvious for
"one active control number per account" without also locking out
legitimate concurrent reads), and the constraint-based approach gives the
same correctness guarantee with less code and no lock contention on the
happy path.

**Consequences:** Every future idempotent-creation feature (payments,
webhook processing — Phase 3) should follow this same three-part shape
rather than inventing a new idempotency mechanism per domain. Tested in
`apps/customers/tests/tests.py`, `apps/billing/tests/tests.py`, and
`apps/control_numbers/tests/tests.py`; the DB-level race itself isn't
exercised by a concurrency test yet (would need real parallel DB
connections, not just sequential test calls) — worth adding once a
domain's correctness is sensitive enough to justify the test complexity.

---

## ADR-011: `ControlNumber.bill` is a strict `OneToOneField`; `ControlNumber.customer_account` uses a conditional unique constraint instead

**Decision:** A `Bill` can have at most one `ControlNumber`, ever,
enforced by `OneToOneField` (no conditional exception). A
`CustomerAccount` can have at most one **active** `ControlNumber` at a
time, enforced by `UniqueConstraint(fields=["customer_account"],
condition=Q(status="active"))` — but can accumulate multiple
`CANCELLED`/`EXPIRED` ones over its lifetime, each superseded by a new
active one.

**Reason:** These two ownership modes have genuinely different
lifecycles (see [docs/CONTROL_NUMBER_SPEC.md](docs/CONTROL_NUMBER_SPEC.md)).
A one-time, bill-bound control number has no legitimate reason to be
reissued — a bill is a single, terminal billing event; if its control
number is somehow wrong, the correct fix is to cancel the bill and the
control number goes with it (via `on_delete=CASCADE`), not reissue a
second control number for the same bill. A persistent, account-bound
control number is explicitly designed to be reused across many billing
cycles and must be able to be re-issued after expiry/cancellation without
losing the history of what was issued before.

**Alternatives considered:** Using the same conditional-unique-constraint
pattern for both, i.e. no `OneToOneField` on `bill` either. Rejected —
it would silently permit a "reissued" one-time control number, which
build spec section 10 explicitly warns against ("never silently reused
for another customer/account") and which has no legitimate use case in
this model; making it structurally impossible via `OneToOneField` is
stronger than relying on service-layer discipline to never do it.

**Consequences:** If a genuine future need for "reissue a one-time
control number" emerges (e.g. a compliance requirement to invalidate and
replace a compromised control number), this ADR should be revisited
explicitly rather than the constraint being quietly loosened.

---

## ADR-012: `Bill.transition_to()` enforces status transitions via an explicit table, not free-form status assignment

**Decision:** `Bill.status` is never set directly by application code
(`bill.status = "paid"; bill.save()`); it's only ever changed through
`Bill.transition_to(new_status)`, which checks the target against an
explicit `ALLOWED_TRANSITIONS` dict and raises `ValidationError` for any
transition not listed (e.g. `DRAFT → PAID` directly, skipping `ACTIVE`).

**Reason:** [docs/BILLING_SPEC.md](docs/BILLING_SPEC.md)'s state diagram
is only actually true of the system if something enforces it — a status
field that any code can freely reassign is a diagram in a doc, not a
guarantee. This matters more than usual for a financial-adjacent status
field: `PAID` should only ever be reachable through the paths the
business logic actually intends (once Phase 3 wires payments into it),
not as a side effect of a bug elsewhere setting the field directly.

**Consequences:** Every future status transition (the `Payment` domain
marking a bill `PARTIALLY_PAID`/`PAID` in Phase 3, a scheduled job
marking it `EXPIRED`) must go through `transition_to()`, extending
`ALLOWED_TRANSITIONS` if a genuinely new transition is needed rather than
bypassing the method. This is directly analogous to
`ControlNumber`/`AuditLog`'s pattern of enforcing an invariant at the
model layer rather than trusting every call site to remember the rule
(see ADR-006, ADR-011).

---

## ADR-013: `merchant_reference` generated by KUSANYA, not the provider's own reference, is the key for resolving UNKNOWN payments

**Decision:** `PaymentProviderAdapter.initiate_payment()` requires a
`merchant_reference` argument, generated by
`apps.payments.services.initiate_payment` (as `Payment.merchant_reference`,
set at `Payment.save()` time) *before* the adapter is ever called.
`query_payment()` is keyed by this reference, not by
`provider_reference` (which the provider generates and which may not
exist at all if the initiate response never arrived).

**Reason:** Build spec section 11's "never blindly retry an uncertain
financial transaction" rule is only actually implementable if there's a
reliable way to ask "what happened to the request I sent" *after* losing
the response. If the only lookup key were the provider's own reference,
a payment that timed out before that reference was even received would
be permanently unqueryable — the system would have no honest choice but
to guess, which is exactly the failure mode the rule exists to prevent.
Real payment-provider APIs (mobile money, card gateways, GEPG-style
government e-payment gateways) universally support exactly this pattern
— accepting a caller-supplied reference specifically so the caller can
recover from a lost response — which is why this isn't a mock-only
convenience; it's modeled after how the real integrations will have to
work.

**Consequences:** Every future real provider adapter must actually pass
`merchant_reference` through to the provider's own API in whatever field
that provider calls it (order ID, client reference, etc.) — an adapter
that doesn't wire this through would silently break UNKNOWN-payment
recovery for that provider. Worth a dedicated adapter-conformance test
once a second (real) adapter exists, rather than trusting this by
inspection.

---

## ADR-014: Inbound callback idempotency is enforced by a database constraint on `(provider, external_event_id)`, not by re-checking payment status alone

**Decision:** `apps.payments.models.PaymentCallbackEvent` has a
`UniqueConstraint(provider, external_event_id)`. `process_callback()`
attempts to INSERT a new event row *before* doing anything else; a
second delivery of the same event ID hits that constraint and is
rejected immediately, before any status transition or webhook dispatch
is even attempted.

**Reason:** Relying solely on "is the payment already in the target
status" (a status-equality no-op check, which also exists — see
`_apply_outcome`) is not sufficient on its own: it protects against
reprocessing the *same outcome* twice, but doesn't distinguish "this
exact event was already handled" from "a different event happens to
report the same outcome," which matters for audit/debugging fidelity
(build spec section 29's audit requirements) even when the financial
effect would be identical either way. Having both layers means the
event-log guarantee is correct on its own even before considering
whether the status-equality shortcut kicks in.

**Alternatives considered:** Deduplicating in application code by
querying for an existing event before inserting (check-then-create).
Rejected for the same reason as ADR-010 — it has a race window under
concurrent delivery, which is a real scenario for webhooks (providers
commonly fire retries aggressively, sometimes in near-parallel).

**Consequences:** A provider that doesn't supply a stable
`external_event_id` per logical event (some don't, or reuse IDs
inconsistently) can't be protected by this constraint alone — that
provider's real adapter would need its own additional idempotency
strategy (e.g. hashing the payload) layered on top when it's built.

---

## ADR-015: Webhook delivery is deferred via `transaction.on_commit`, never enqueued directly inside the triggering transaction

**Decision:** `apps.webhooks.services.dispatch_event` wraps the Celery
`.delay()` call in `django.db.transaction.on_commit(...)` rather than
calling it directly.

**Reason:** The Celery worker is a separate OS process from the web
request (or the request that triggered the event). If the task were
enqueued immediately, a sufficiently fast worker could start processing
it — reading the `WebhookDelivery` row, or worse, related rows like
`Payment`/`Bill` — before the enqueuing transaction actually commits, or
even after it never commits at all (an exception later in the same
request rolls everything back, but the already-enqueued task still
fires). `transaction.on_commit` guarantees the callback only runs after
a successful commit, closing that race entirely.

**Consequences:** Any future code that enqueues a Celery task as a
side effect of a database write should follow the same pattern — this is
now precedent, not just a one-off webhook detail. Tests exercise
`dispatch_event`'s delivery-creation logic directly (patching
`deliver_webhook.delay`) rather than asserting on `on_commit` timing
itself, since pytest-django's `TestCase`/transaction-wrapped tests would
need `captureOnCommitCallbacks` to observe it — acceptable for Phase 3;
worth adding if `on_commit` behavior itself ever needs direct test
coverage.

---

## ADR-016: `PaymentProvider`/`PaymentChannel` are platform-level catalog models, not tenant-scoped

**Decision:** Unlike almost every other Phase 2/3 model,
`apps.providers.PaymentProvider` and `PaymentChannel` inherit
`apps.core.models.BaseModel`, not `TenantScopedModel`.

**Reason:** "Which payment providers exist and what channels they offer"
is a platform-level fact (KUSANYA integrates with a given provider once),
not something each tenant defines independently — this mirrors how
`Sector` is platform-defined metadata on `Tenant` rather than a
per-tenant concept (see [MULTI_TENANCY.md](docs/MULTI_TENANCY.md)).
Making these tenant-scoped would incorrectly imply every tenant needs its
own copy of the same catalog row.

**Consequences:** *Which* tenants are permitted to use a given provider,
and any tenant-specific provider configuration (merchant codes, credential
references), is a distinct, not-yet-modeled concept — deferred to Phase 4
as part of `CollectionAccount` (see build spec section 6's universal data
model and [docs/SETTLEMENT_SPEC.md](docs/SETTLEMENT_SPEC.md)), since that's
when routing collected funds to a specific tenant's collection account
actually starts to matter. Phase 3 has exactly one provider (mock) that
every tenant can use unconditionally, so this gap has no present
consequence — it will before a second (real) provider is added.

**Update (Phase 4):** `CollectionAccount` was *not* built in Phase 4 —
see ADR-019 below for why, and what settlement does instead without it.

---

## ADR-017: `RevenueEvent` is recorded for every event in the vocabulary, including zero-fee ones — not only charged events

**Decision:** `apps.revenue.services` calls a `record_*` function for
*every* control-number/payment outcome (`CONTROL_NUMBER_REUSED`,
`PAYMENT_FAILED`, `PAYMENT_DUPLICATE` included), not only the two that
actually charge a fee. Zero-amount events get a `RevenueEvent` row but
**no** `LedgerEntry`.

**Reason:** Build spec section 4 explicitly lists all seven event types
("Revenue events must include at minimum: CONTROL_NUMBER_CREATED,
PAYMENT_SUCCESSFUL, PAYMENT_REVERSED, PAYMENT_REFUNDED, PAYMENT_FAILED,
PAYMENT_DUPLICATE, CONTROL_NUMBER_REUSED") as things the revenue engine
must handle — not just the ones that move money. Recording the zero-fee
events too makes "how many control numbers were reused this month" or
"how many payments failed" real, queryable platform metrics instead of
information that only existed transiently in an audit log line. Not
posting a `LedgerEntry` for them is the other half of the same judgment
call: a ledger line with amount 0 carries no financial information and
would just be noise in a financial ledger that's supposed to be exactly
reconcilable — the *count* of zero-fee events is available from
`RevenueEvent` directly.

**Consequences:** Any future report or dashboard built on "platform
activity volume" (as opposed to "platform revenue") should query
`RevenueEvent` across all event types, not `LedgerEntry` — the two serve
different questions and only overlap for the non-zero events.

---

## ADR-018: Reconciliation is scoped to per-reference provider checks, not a bulk statement import

**Decision:** `apps.reconciliation.services.run_reconciliation()` only
checks references KUSANYA already has a `Payment` row for — it calls
`PaymentProviderAdapter.reconcile()`/`query_payment()` per payment. It
does **not** attempt to enumerate everything the provider processed and
look for KUSANYA-side gaps.

**Reason:** `PaymentProviderAdapter` (Phase 3, see
[docs/PAYMENT_PROVIDER_ARCHITECTURE.md](docs/PAYMENT_PROVIDER_ARCHITECTURE.md))
was deliberately modeled after what the build spec's own interface list
supports — `reconcile()` is per-transaction, not a bulk statement/ledger
pull, because that's what section 12 specifies and what most real
provider integrations actually offer (a "query this reference" endpoint,
not a full statement API). Building bulk-import reconciliation against an
interface that doesn't have a bulk-list method would mean inventing
provider capabilities that may not exist for a real provider — exactly
what build spec section 43 forbids.

**Consequences:** This means one specific failure mode is *not*
detectable by Phase 4's reconciliation: a transaction that happened at
the provider that KUSANYA never recorded at all (no `Payment` row, so
nothing to check `reconcile()` against). Detecting that requires a
provider statement/settlement-file import — a genuinely different
capability, not a gap in the current implementation, and not built.
Documented explicitly in
[docs/RECONCILIATION_SPEC.md](docs/RECONCILIATION_SPEC.md) so it's never
silently assumed to be covered.

---

## ADR-019: Settlement claims payments directly (`Payment.settlement_batch`), without a `CollectionAccount` model

**Decision:** `SettlementBatch` selects unsettled `SUCCESSFUL` payments
for a given tenant+provider+period directly from `Payment`, and claims
them via a `Payment.settlement_batch` FK (added to the Phase 3 `Payment`
model). No `CollectionAccount` model was introduced, despite ADR-016
flagging it as the natural Phase 4 home for "which tenants may use which
provider, with what configuration."

**Reason:** Once actually building settlement, the only thing Phase 4
needed from "which provider is this tenant settling through" was already
answerable from `Payment.provider` (every payment already records which
provider processed it) — a `CollectionAccount` model would have added a
layer of indirection (tenant → collection account → provider) that
nothing in Phase 4 actually reads yet, since there's exactly one provider
and every tenant can use it unconditionally (ADR-016). Building the model
now, unused, would be exactly the kind of speculative scaffolding
principle 9/section 42 warns against ("do not attempt to write every
feature in one giant uncontrolled generation").

**Consequences:** `CollectionAccount` (or an equivalent) becomes
necessary the moment either becomes true: (a) a second real provider is
integrated and a tenant needs to choose/configure which one(s) they
accept, or (b) tenant-specific provider credentials/merchant codes need
to be stored per tenant rather than assumed global. Revisit this ADR at
that point rather than retrofitting `CollectionAccount` speculatively
now.

---

## ADR-020: `Tenant.fee_refund_policy` lives on `Tenant`, not a separate revenue-config model

**Decision:** The configurable accounting treatment build spec section 4
requires for reversal/refund fee handling
(`CLAWBACK`/`RETAIN` — see [docs/PRICING_MODEL.md](docs/PRICING_MODEL.md))
is a single `CharField` with choices added directly to the Phase 1
`Tenant` model, not a new `RevenuePolicy`/`TenantRevenueConfig` model.

**Reason:** It's one setting, tenant-scoped 1:1, with no independent
lifecycle of its own (it doesn't get created/approved/versioned
separately from the tenant) — a dedicated model would be a
one-column table joined 1:1 to `Tenant` for no structural benefit. Every
other tenant-level configuration introduced so far (`default_currency`,
`fee_refund_policy`) follows the same pattern: a field on `Tenant`, not a
satellite config model, until enough related settings accumulate to
justify grouping them.

**Consequences:** If Phase 4+ needs several more revenue-related
per-tenant settings, revisit whether they belong grouped in a dedicated
config model rather than continuing to add fields to `Tenant` — a `Tenant`
model that accumulates too many unrelated concerns becomes its own
maintenance problem. Not yet at that threshold.

---

## ADR-021: Default notification templates are code constants (`apps.notifications.defaults`), not database rows

**Decision:** Every (event type, channel) pair's default copy lives in a
Python dict in `apps/notifications/defaults.py`. `NotificationTemplate`
(a real, tenant-scoped, database-backed model) exists only for a
tenant's *override* of a specific pair — most tenants have zero rows in
that table and get entirely correct behavior from the code defaults.

**Reason:** The alternative — seeding every tenant with a full set of
default template rows at creation time (mirroring, e.g., the
`providers.PaymentProvider` catalog seed from Phase 3) — would mean (a) a
schema/data migration every time a default needs wording fixed, since
every tenant's copy of that row would need updating, not just one source
of truth, and (b) an empty-seeming `NotificationTemplate` table for the
common case of a tenant that never customizes anything looking like
missing data rather than "using the default, as intended." Keeping
defaults in code and overrides in the database makes "does this tenant
have a customization" a direct, honest query
(`NotificationTemplate.objects.filter(tenant=..., event_type=...,
channel=...)`) instead of "does this row still equal the default text."

**Consequences:** Changing default copy is a code change (reviewed,
tested, deployed) rather than a data migration — appropriate, since
wording changes are a product decision with the same review bar as any
other code change. A tenant wanting a permanent customization creates
exactly one `NotificationTemplate` row for exactly the (event, channel)
pair they want to change; every pair they don't customize continues to
track the code default automatically, including future default wording
improvements — which would NOT be true if every tenant had been seeded a
copy at creation time.

---

## ADR-022: Reports are focused per-domain views, not a generic report-builder engine

**Decision:** `apps/reports/` contains one view function per report
(bills, payments, collections, outstanding balances, audit events), each
querying its own specific model(s) with its own specific filters. There
is no `Report`/`ReportDefinition` model, no generic "pick a model, pick
filters, pick columns" builder.

**Reason:** Build spec section 27 names specific reports with specific,
mostly-different filter sets (a "notifications" report doesn't need a
"revenue source" filter; an "audit events" report doesn't need a
"channel" filter). A generic report-builder engine capable of expressing
all of these would be a meaningfully larger, more complex system — a
small query-and-filter DSL, effectively — for a set of reporting needs
that four phases of concrete domain models have already fully
enumerated. Building the generic version speculatively, before a second
concrete need proves the concrete version doesn't scale, would be exactly
the kind of premature abstraction principle 9 warns against.

**Consequences:** Every new report is a new, small, reviewable view
function — not a configuration entry in a generic engine. If report
requirements grow enough that "one Python function per report" stops
scaling (e.g., tenants wanting to define their own custom reports), that
would be a deliberate, justified new system to design then — not
something to have spent Phase 5 building speculatively against a need
that doesn't exist yet.

---

## ADR-023: `ApiCredential` is a distinct model, not a Django `User` with an API-key flag

**Decision:** External API authentication (`apps/api/models.py::ApiCredential`)
is its own model — `key_id` + hashed `secret`, tenant-scoped — with no
relationship to `apps.users.User` beyond an optional `created_by` FK
recording which portal user generated it.

**Reason:** A `User` in this codebase carries a whole identity stack that
makes no sense for a server-to-server integration: a password (a
credential an ERP integration doesn't have or need), session-based login
(an integration never "logs in" interactively), `TenantMembership`/RBAC
roles designed around a person acting through the portal UI, and audit
semantics ("who did what" — for an API credential, "what integration"
is the more honest question than "which person," since the same
credential is typically shared by one integration's server process, not
tied to an individual). Modeling the credential as its own thing keeps
"a person with portal access" and "a system with API access" as the two
genuinely different concepts they are, rather than overloading `User`
with an `is_api_key` boolean and a pile of fields that are meaningless
for one case or the other.

**Consequences:** `ApiKeyAuthentication` returns `(AnonymousUser(),
credential)` from DRF's `authenticate()` — `request.user` is never a real
user for an API-authenticated request, only `request.auth` (the
credential) and `request.tenant` (set directly from it) carry meaning.
Anywhere in application code that assumes `request.user` is always a
real, DB-backed `User` (there is no such code today, but it's a trap for
future code) needs to instead branch on whether the request came through
session auth or API-key auth, or use `getattr(request, "api_credential",
None)` as the API-context signal.

---

## ADR-024: Credential rotation is immediate replacement, not a grace-period overlap

**Decision:** `apps.api.credential_services.rotate_credential()` replaces
a credential's secret in place — the old secret stops authenticating the
instant the function returns. There is no window where both the old and
new secret work simultaneously.

**Reason:** A grace-period rotation (common in mature API platforms —
"the old key keeps working for 24 hours while you migrate") requires
storing and validating against *two* secrets per credential for some
period, plus a mechanism to expire the old one on a schedule — real
complexity or Celery beat scheduling that Phase 6 has no existing
precedent for (the closest analog, `apps.control_numbers.services.expire_overdue`,
also isn't wired to a schedule yet — see docs/CONTROL_NUMBER_SPEC.md).
Building that scaffolding for one feature, speculatively, rather than
when a second scheduled-expiry need makes the investment clearly worth
it, would be exactly the premature complexity principle 9 warns against.

**Consequences:** A tenant rotating a credential currently in active use
by a live integration causes that integration to start failing
authentication immediately upon rotation, until its configuration is
updated with the new secret. The portal's rotation confirmation page
says this explicitly. The safe rotation procedure with today's
implementation is: create a **second** `ApiCredential` (a tenant can have
as many active credentials as they want — nothing in the model limits
this), migrate the integration to it, confirm it's working, *then* revoke
the first one — never rotate a credential that's currently serving live
traffic. Worth revisiting if/when a real integration partner specifically
needs zero-downtime rotation.
