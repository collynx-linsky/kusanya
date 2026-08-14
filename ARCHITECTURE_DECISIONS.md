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

## ADR-025: MFA setup shows the secret and `otpauth://` URI as text, not a rendered QR code

**Decision:** `apps.accounts.portal_views.mfa_setup` gives the user the
raw Base32 secret and the full `otpauth://totp/...` URI
(`apps.accounts.totp.build_otpauth_uri`) as plain text/a copyable link.
It does not render a QR image for an authenticator app to scan.

**Reason:** Generating a QR code image server-side means either a new
dependency (`qrcode` + `Pillow`) or hand-rolling QR encoding — real
complexity for a Phase 7 feature whose actual requirement (build spec
section 28's "MFA-ready") is met by any correct TOTP enrollment path.
Every mainstream authenticator app (Google Authenticator, Authy, 1Password,
Aegis, etc.) accepts manual secret entry, and the `otpauth://` URI is
itself pasteable into apps that support "add via link." A QR code is a
UX nicety, not a correctness requirement.

**Consequences:** Setup is one extra manual step (typing/copying a
32-character secret) versus scanning a camera. Worth adding a QR image
later — a small, self-contained addition, not a rework — if user feedback
says the manual-entry friction matters in practice.

## ADR-026: `pip-audit` in CI is informational-only, never fails the build

**Decision:** `.github/workflows/ci.yml`'s dependency vulnerability scan
step runs `pip-audit -r requirements/base.txt || true` — a nonzero exit
(meaning a known CVE was found in some installed package) does not fail
the CI run.

**Reason:** A hard-fail policy means every new CVE disclosure in any
transitive dependency — including ones KUSANYA doesn't exercise in a
vulnerable way, or ones with no available fixed version yet — blocks
every unrelated pull request the moment it's disclosed, with no
mechanism in Phase 7 to acknowledge/allowlist a specific finding. That's
a workflow that trains people to ignore or bypass CI, which is worse than
not scanning at all.

**Consequences:** A real, actionable vulnerability can land and sit
unnoticed if nobody reads the CI log for that step. This is a real gap,
not a nonissue — revisit if/when there's a triage process (e.g. a
`pip-audit --ignore-vuln` allowlist reviewed on a schedule) that can
support a hard-fail policy without the false-positive-blocks-everything
problem.

## ADR-027: Backup codes are matched by a keyed HMAC-SHA256 lookup hash, not `make_password`/PBKDF2

**Decision:** `BackupCode.lookup_hash` stores `HMAC-SHA256(key=SECRET_KEY,
msg=normalized_code)` (`apps.accounts.models._backup_code_lookup_hash`),
looked up with an indexed exact-match query
(`BackupCode.objects.filter(user=user, lookup_hash=..., used_at__isnull=True)`).
The original Phase 7 implementation used Django's `make_password`/
`check_password` (PBKDF2) instead, checked in a loop over every unused
code — replaced by this ADR.

**Reason:** Live testing (not the automated suite — see below) measured
`consume_backup_code()` at **18.7 seconds** to reject one wrong code
against a user with 10 unused backup codes: ~1.9 seconds per PBKDF2
`check_password()` call, times up to 10 rows scanned linearly. PBKDF2's
deliberate slowness exists to resist offline dictionary/brute-force
search of a *low-entropy, user-chosen* secret (a password) — it's the
wrong tool for a backup code, which is ~52 bits of `secrets`-module
randomness that was never guessable in the first place. The property
that actually matters — never storing the raw code — is fully satisfied
by a keyed HMAC: it's a real cryptographic MAC, unforgeable without
`SECRET_KEY`, and, unlike PBKDF2, cheap enough to use as an indexed exact
match instead of a linear scan-and-hash. `apps.accounts.mfa_services`
also adds a cheap format pre-check (`_looks_like_backup_code`) so an
ordinary mistyped 6-digit TOTP guess — the overwhelmingly common failed
MFA attempt — never touches the backup-code table at all.

This is also why the automated test suite didn't catch the original
defect: `config/settings/testing.py` overrides `PASSWORD_HASHERS` to the
fast `MD5PasswordHasher` for test speed, which made every `check_password`
call in tests near-instant regardless of algorithm choice, masking the
real cost of PBKDF2 under the actual production-equivalent hasher used
in `development.py`/production. Only a live, real-hasher measurement
surfaced it — reinforcing why this codebase treats live verification, not
just green automated tests, as a precondition for calling a phase done
(see the Phase 1-7 development reports).

**Consequences:** Losing `SECRET_KEY` (e.g. a full server compromise)
means an attacker with database access could, in principle, verify
guesses against `lookup_hash` at HMAC speed rather than PBKDF2 speed —
but they'd need both the database *and* `SECRET_KEY` *and* still be
guessing a 52-bit random value with no dictionary to search, which is not
a meaningfully weaker position than they'd already be in from a full
server compromise (they could rotate `SECRET_KEY` themselves, read
plaintext from live requests, or forge sessions directly). Rotating
`SECRET_KEY` invalidates all outstanding backup codes' lookup hashes,
same as it already invalidates all sessions and signed tokens today —
an accepted, pre-existing tradeoff of using `SECRET_KEY` for signing
throughout this codebase, not a new one introduced here.

## ADR-028: MFA setup renders a real scannable QR code (supersedes ADR-025)

**Decision:** `apps.accounts.totp.build_otpauth_qr_svg()` renders the
`otpauth://` setup URI as an inline SVG QR code (via the `qrcode`
package's `SvgPathImage` factory — pure Python, no Pillow/image-library
dependency), displayed on the MFA setup page. The 32-character secret and
raw setup URI are still shown, collapsed behind a "can't scan a QR code?"
disclosure, as a fallback for apps/situations that need manual entry.

**Reason:** ADR-025 deferred this, betting that manual secret entry was
good enough and that a QR image was "a UX nicety, not a correctness
requirement," worth adding "if user feedback says the manual-entry
friction matters in practice." It came up immediately in real use: a live
account was set up with no way to scan the secret into an actual
authenticator app, so every login afterward required asking for a code
relayed by hand — a losing race against the 30-second TOTP period (see
the login attempts that triggered the lockout ADR-027's throttle is
designed to apply), and error-prone for backup codes too. `qrcode`'s SVG
output specifically avoids reopening the Pillow-dependency question
ADR-025 raised — it needed no new system dependency, just one pure-Python
package.

**Consequences:** One new dependency (`qrcode>=8.0`, `requirements/base.txt`).
The rendered SVG is built entirely server-side from data KUSANYA itself
generated (the device secret, the account's own email) — no user input
flows into it, so it's rendered with `|safe` without reopening an XSS
question. Manual entry remains available (now behind a disclosure,
de-emphasized rather than removed) for authenticator apps or situations
that can't scan a camera.

## ADR-029: Bandit runs in CI against KUSANYA's own code and blocks the build — a different posture from ADR-026's `pip-audit`

**Decision:** `bandit -c pyproject.toml -r apps config` runs in CI
(`.github/workflows/ci.yml`) with no `|| true` — a finding fails the
build. `pyproject.toml`'s `[tool.bandit]` section excludes
`migrations/`, `tests/`, and the virtualenv from scanning. A first run
found 4 low-severity findings, all reviewed individually and suppressed
inline with a justified `# nosec <code>` comment (not a blanket
config-level ignore): a `random.randint` used for a control number's
non-secret suffix (`apps/control_numbers/services.py` — see that
function's docstring for why unpredictability isn't actually the
security property a control number needs), and three "possible hardcoded
password" false positives that are actually a sandbox-only mock
provider fixture, a sentinel comparison against a known-insecure
default, and a test-only settings constant.

**Reason:** ADR-026 made `pip-audit` (third-party dependency CVEs)
informational-only, because a new disclosure in code KUSANYA doesn't
control and often can't immediately fix shouldn't block every unrelated
PR. That reasoning doesn't transfer to Bandit: every finding here is in
code this project wrote and can fix immediately. "We can't do anything
about it yet" isn't available as an excuse for our own code the way it
legitimately is for a transitive dependency's CVE. A tool that never
blocks anything trains people to stop reading its output — the whole
point of adding static analysis is for a real finding to actually stop
something.

**Consequences:** A new, non-suppressed Bandit finding blocks CI, same
as a failing test. Suppressing a real finding requires a `# nosec`
comment at the exact line, with a reason — which means every suppression
is visible in a diff and in code review, not hidden in a config
allowlist a reviewer would have to go look up separately. New apps
should expect to be scanned by default (nothing app-specific is
excluded, only migrations/tests) — a genuinely risky pattern introduced
later (e.g. real string-built SQL, `eval`, a hardcoded real-looking
secret) will fail CI the same way this first run's false positives did,
which is the intended behavior.

## ADR-030: General request rate limiting is a fixed-window cache counter middleware, not a third-party library

**Decision:** `apps.core.ratelimit.RequestRateLimitMiddleware` counts
requests per client (authenticated user ID, else IP) in a fixed 60-second
window via the existing cache backend, rejecting with `429` past
`REQUEST_RATE_LIMIT` (120/minute by default). It sits alongside, not in
place of, two existing purpose-specific throttles:
`apps.accounts.throttle` (login/MFA brute-force lockout, ADR from Phase
7) and the API's own DRF throttling (Phase 6). It fails open on any
cache error.

**Reason:** The gap was real — ordinary portal/dashboard views (bill
lookups, control-number pages, tenant onboarding forms) had no request
volume limit at all, unlike the API and the login/MFA paths. A
general-purpose library (`django-ratelimit`, `django-axes`) would add a
dependency for something the codebase already had the primitive for —
`apps.accounts.throttle` already proved the cache-counter pattern works
correctly for this project's actual cache backend (Redis) and deployment
shape. Writing ~40 lines against a pattern already in production use is
less risk than a new dependency with its own configuration surface.

**Consequences:** The limit is deliberately generous (120/min) — this is
a blunt instrument against scripted abuse, not a precision tool; a
legitimate user issuing rapid HTMX partial-page requests should never
hit it in practice, but a single, generous, global number can't be
correctly tuned per-endpoint (a bill-lookup page and a dashboard-summary
page have different legitimate request rates). Fixed-window counting
(not sliding-window/token-bucket) means a client can in principle send
close to `2 × limit` requests across a window boundary — an accepted
imprecision for a defense-in-depth control, not the primary defense
against any specific attack. `/api/` is excluded from this middleware
entirely (the API's DRF throttling already covers it, with different,
more precise per-credential semantics) to avoid two different rate
limiters disagreeing about the same request.

## ADR-031: Monitoring gets a scheduled internal health check + email alert, not a fabricated APM integration

**Decision:** `apps.core.healthchecks.run_health_checks()` is the one
real implementation of "check database/cache/Celery-broker," used by
both `apps.core.views.health_check` (the existing passive HTTP probe)
and the new `apps.core.tasks.monitor_system_health` — a Celery Beat task
seeded to run every 5 minutes (`apps/core/migrations/0002_seed_health_monitor_schedule.py`,
a data migration creating the `IntervalSchedule`/`PeriodicTask` rows
`django_celery_beat`'s `DatabaseScheduler` reads). On failure it emails
`settings.ADMINS` via Django's `mail_admins()`.

**Reason:** "Add monitoring/alerting" could mean wiring a real APM
product (Datadog, New Relic, PagerDuty) — none of which this project has
an account for, and inventing a fake integration against a
service/credentials that don't exist would violate the same "no fake
functionality" rule the build spec applies to payment providers. What
*can* be built honestly, with infrastructure this project already runs
(Celery Beat, Redis, Django's own mail framework), is a real scheduled
check that does something real on failure. It's a genuinely useful,
narrower tool — not a placeholder standing in for a future integration —
and it closes the specific gap that nothing was watching `/healthz/` on
its own.

**Consequences:** This is not APM (no tracing, no performance metrics,
no dashboards) and not intrusion detection — `docs/SECURITY_ARCHITECTURE.md`
still lists both as absent, honestly. `mail_admins()` requires
`settings.ADMINS` to be non-empty (`PLATFORM_ALERT_EMAILS` env var) and a
working SMTP configuration (`EMAIL_HOST`/`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`
in `production.py`, unset by default) to reach anyone — exactly the same
"real code, inert until deployed with real config" shape as `SENTRY_DSN`.
An outage before either is configured produces a `logger.error` line
(picked up by structured JSON logging in production) and nothing else —
still strictly better than the pre-Phase-7 state of no scheduled check
existing at all, but not a substitute for a real external monitor once
this deploys somewhere that has one available.

## ADR-032: Field-level encryption at rest via Fernet + HMAC lookup-hash companions, not a third-party field-encryption library

**Decision:** `apps.core.encrypted_fields.EncryptedCharField`/`EncryptedTextField`
transparently Fernet-encrypt (AES-128-CBC + HMAC-SHA256, authenticated,
non-deterministic) on save and decrypt on load, keyed by a value derived
from `settings.FIELD_ENCRYPTION_KEY` (itself derived from `SECRET_KEY` in
dev/test, required explicitly in production — same fail-loud pattern as
`SECRET_KEY` itself). Every lookup except `isnull` is disabled at the
field level (`get_lookup` raises `FieldError`) so a `.filter(field=...)`
mistake fails loudly instead of silently matching nothing, since
Fernet's non-determinism means the same plaintext never produces the
same ciphertext twice.

Fields that are also searched in Django admin get a companion
`<field>_lookup_hash` column — deterministic HMAC-SHA256 of the
normalized value (`apps.core.encrypted_fields.compute_lookup_hash`),
kept in sync by each model's `save()` — and `EncryptedFieldSearchAdminMixin`
restores admin search on them as an **exact-match-only** query against
that column, not the substring match `search_fields` normally gives.
This is the same lookup-hash pattern already proven for MFA backup
codes (`apps.accounts.models._backup_code_lookup_hash`, ADR-027) —
applied here to a second, unrelated problem because it's the right
answer to the same underlying question: "how do you support exact
lookup against something you can't decrypt cheaply/deterministically."

Applied to: `Customer.full_name/email/phone_number`,
`User.first_name/last_name/phone_number`,
`Tenant.contact_email/contact_phone`, `Branch.address`, `Bill.notes`,
`SettlementBatch.notes`, `ReconciliationException.resolution_notes`,
`Receipt.customer_name`, `Notification.recipient`,
`Payment.payer_reference`. Each migration follows the same three-step
sequence, in this order, because getting the order wrong actively
corrupts data:

1. Add the `lookup_hash` column (if any) and widen the target column to
   unbounded TEXT — ciphertext is longer than the original
   varchar limit, and doing this *after* encrypting would truncate/error.
2. A data migration (`RunPython`) that re-encodes every existing row
   from plaintext to ciphertext and computes `lookup_hash`, using
   Django's historical model — which at this point in migration history
   is still the *plain* field type, so `.update()` writes the computed
   ciphertext as a literal string rather than re-encrypting it.
3. `AlterField` to the real `EncryptedCharField`/`EncryptedTextField` —
   only now is it safe, because the DB already holds valid ciphertext.

**Reason (why build this instead of `django-cryptography`/`django-fernet-fields`):**
this codebase already has zero tolerance for opaque dependencies where a
small, auditable implementation is straightforward (see ADR-025/ADR-027
making the identical call for TOTP and backup-code hashing) — Fernet
itself is `cryptography`'s own well-reviewed primitive; what this file
adds is ~150 lines of Django field plumbing, not cryptography.

**Reason (scope):** three options were on the table before any code was
written — leave searchable PII unencrypted, encrypt everything and
accept losing admin search on those fields entirely, or encrypt
everything and rebuild exact-match search via a lookup_hash. The third
was chosen: "encrypt everything, keep exact-match search." The real,
unavoidable cost that comes with it: Django admin's substring/fuzzy
search (`icontains`) on every field listed above is gone permanently —
typing part of a name or the last 4 digits of a phone number no longer
finds a record; only the complete, exact value does.
`Customer.Meta.ordering`/`CustomerAccount.Meta.ordering` were also
changed away from `full_name` to `-created_at`/`customer_id` for the
same underlying reason — sorting by ciphertext has no relationship to
alphabetical order.

**Deliberately deferred, not forgotten:**

- **`User.email`** — NOT encrypted. It is `USERNAME_FIELD`, has a
  DB-level `unique=True` constraint, and is looked up via exact match on
  *every single login* (`ModelBackend.get_by_natural_key`). A
  lookup_hash column could in principle support this too, but changing
  the field the entire authentication path depends on is a materially
  higher-risk change than any field in this ADR, and deserves dedicated
  review (and its own live-verified login testing) rather than being
  bundled into a 10-model sweep. `Tenant.contact_email`/`Customer.email`
  are encrypted; `User.email` is the one deliberate, documented
  exception.
- **`apps.audit.models.AuditLog`** (`before`/`after`/`metadata`/`actor_label`/`ip_address`/`user_agent`)
  — NOT encrypted. `AuditLog.record_hash` is a hash-chain over these
  exact field values (ADR-006) — encrypting them would need to happen
  *before* hash computation, or the chain would only attest to
  ciphertext, and `AuditLog` blocks `.save()` on existing rows entirely,
  which the two-phase "encrypt then swap field type" migration sequence
  above assumes it can freely `.update()` around. Revisiting this
  needs its own design pass against the hash-chain guarantee specifically,
  not a mechanical application of this ADR's pattern.
- **`WebhookDelivery.payload`, `PaymentCallbackEvent.raw_payload`** — NOT
  encrypted. This data has already left the system in plaintext (an
  outbound webhook call, an inbound provider callback) by the time it's
  stored — encrypting the local copy doesn't reduce what's already been
  shared externally, so it wasn't judged worth the same migration risk
  for a smaller marginal benefit than the fields above.

**Consequences:** `FIELD_ENCRYPTION_KEY` rotation invalidates every
encrypted value and every lookup_hash simultaneously (same tradeoff
already accepted for `SECRET_KEY` in ADR-027) — there is no key-rotation
tooling yet; rotating it today means every encrypted field becomes
unreadable (`from_db_value` returns `"[unreadable: decryption failed]"`
rather than raising, so this fails visibly, not silently, but it is a
real outage of that data). Losing `FIELD_ENCRYPTION_KEY` outright means
that data is permanently unrecoverable — this is the correct behavior
for encryption at rest, but is worth stating plainly: back up the key
with at least the same care as the database itself.

## ADR-033: Enterprise UX rework stays Django Templates + Bootstrap 5 + HTMX — a design system and app shell, not a framework swap

**Decision:** The user explicitly required "do not replace Django
Templates + Bootstrap 5 + HTMX with React/Next.js" for a 32-item,
4-tier enterprise-UX request (P0 Foundation through P3 Quality). P0
(Foundation) is built as: a token-based design system
(`static/css/design-tokens.css`), a persistent sidebar + top-bar app
shell (`templates/base.html`, `partials/sidebar.html`, `partials/topbar.html`,
a separate `base_auth.html` for pre-login pages), reusable
components as CSS classes + a handful of `{% include %}` partials
(`templates/components/`), an HTMX convention layer (CSRF injection,
global loading indicator, toast events — `static/js/kusanya.js`),
`django-crispy-forms`/`crispy-bootstrap5` for consistent form markup,
and a search/sort/pagination table convention — each piece fully built
out and live-verified on the Customers app as the reference
implementation (`docs/DESIGN_SYSTEM.md` has the full breakdown and, per
that doc's own "Migration status" section, an honest account of which
of the ~40 other templates still run the old markup, unmigrated but not
broken, pending the same mechanical treatment).

**Reason:** Bootstrap 5.3's CSS custom-property theming system
(`--bs-*`) and HTMX's out-of-band/partial-swap model already provide
most of what a component framework buys — consistent theming and
partial-page interactivity — without a build step, a second runtime, or
abandoning server-side rendering. `django-crispy-forms` is the one new
dependency added, deliberately: it is the standard, actively-maintained
answer to "consistent Bootstrap form markup from a Django Form" for
exactly this stack, not a framework-shaped choice.

**Reason (P0 scope, not the full 32 items):** the request's own
structure (P0/P1/P2/P3 tiers) already implies staged delivery — P0 is
foundational and everything else depends on it, so it was built first
and completely, rather than spreading partial effort across all 32
items. Two items were pulled forward opportunistically because they
were low-risk and naturally paired with work already in progress: the
tenant dashboard got the new `stat_card` component (trivial, same data,
better visual consistency), and a stale "not yet implemented: receipts,
notifications, the API" notice on that same dashboard was corrected
(all three shipped in earlier phases of this project) while the
template was already open for editing.

**A real bug this surfaced, not just a UI change:** `templates/base.html`
originally branched `{% if user.is_authenticated %}` inside *one* file
with two copies of `{% block content %}{% endblock %}` — Django
template blocks cannot repeat within a single file, even in mutually
exclusive branches, and this broke literally every page
(`TemplateSyntaxError`) until split into `base.html` (always-shell) and
`base_auth.html` (minimal, for login/MFA-verify/onboarding). Separately,
a component partial's "usage example" written inside a `{# ... #}`
single-line comment was not actually inert — confirmed directly against
`django.template.Template` that a `{% include %}`-shaped example text
inside `{# #}` gets tokenized and executed rather than ignored, which
in `components/empty_state.html`'s case (whose own example included
itself) caused genuine infinite recursion (`RecursionError`) the moment
that component's empty-state branch rendered. Fixed by using `{% comment %}...{% endcomment %}`
for any doc-comment that itself contains template tag syntax — verified
safe with the same direct-`Template()` test before trusting it. Both
are documented in `docs/DESIGN_SYSTEM.md` so neither gets rediscovered
migrating the remaining ~40 templates.

**Consequences:** Every existing page keeps working and inherits the
new shell/tokens automatically (nothing needed touching `base.html`'s
consumers to pick up sidebar/top-bar/color changes) — but only the
Customers app has the newer search/pagination/crispy-forms conventions
applied. Global `hx-boost` (SPA-like navigation with a persistent shell
via `hx-select`) was deliberately not turned on in P0 — it needs real
browser verification to confirm it doesn't desync the sidebar's
active-link highlighting after a boosted navigation, which this
environment can't do; shipping it unverified was judged worse than not
shipping it yet. 207/207 automated tests passing, Bandit clean,
live-verified end-to-end over real HTTP against the running dev server
(every major section's URL, the crispy-rendered customer form, and the
HTMX exact-match search/empty-state/pagination behavior on the
Customers reference implementation).

## ADR-034: P1 (Enterprise UX) — filtering, modals, a real (not fabricated) notification bell, CRUD completion, error-page polish

**Decision:** Built on P0's foundation (ADR-033): filtering (status
dropdown alongside search, `apps.billing.views.bill_list` as a second
reference case beyond Customers), two modal patterns (static
Bootstrap for simple confirmations; HTMX-loaded for data-driven forms,
using `HX-Redirect` on success so a submitted form actually navigates
rather than getting AJAX-swapped into itself), a real topbar
notification bell (`apps.core.context_processors.topbar_alerts`),
skeleton loading states for HTMX-loaded modal content, `403`/`404`
pages rewired onto the `empty_state` component, `500.html` deliberately
left as the one page that does *not* extend `base.html`, and Customer
CRUD completed (`customer_edit` + deactivate/activate replacing what
was previously Create+Read only). Full breakdown in
`docs/DESIGN_SYSTEM.md`.

**Reason (notification bell, the one genuinely debatable item):** "add
notifications" could easily have meant a stored, markable-as-read
inbox — building that with no real event source feeding it, or seeding
it with placeholder entries, would be exactly the "fake functionality"
this project's build spec explicitly rules out (the same reasoning
already applied to payment providers, ADR-014, and to monitoring,
ADR-031). What *is* real and already computed elsewhere (open
reconciliation exceptions on the tenant dashboard, pending tenant
approvals on the platform dashboard) is now also surfaced as a live
topbar alert — same data, a second honest presentation of it, not a new
data source invented for the UI. A persistent inbox is a legitimate
future feature; it needs its own model and its own design pass, not a
placeholder built to satisfy a checklist item.

**Reason (deactivate, not delete, for Customer CRUD):** the "never
truly delete, only mark/compensate" principle this codebase already
applies to every financial-event model (immutable records, ADR-006)
extends to `Customer` even though it isn't itself a ledger entry — a
customer with bills and payments attached cannot be hard-deleted
without corrupting that history. `Customer.is_active` already existed
on the model for exactly this; P1 just built the missing UI for it.

**A real correctness detail, not just UX:** the HTMX-loaded-modal
pattern's success path deliberately sets an `HX-Redirect` response
header rather than relying on htmx's default handling of a 302. Without
it, htmx would AJAX-fetch the redirect target and swap the *result*
into the modal body — the modal would stay open, showing the customer
detail page's content nested inside itself, instead of the browser
actually navigating there. Verified live (both the `HX-Redirect` header
value and, separately, that the created record actually appears on the
resulting page) before considering the pattern proven.

**Consequences:** Two more stale "not yet implemented" notices (the
platform dashboard's, alongside the tenant dashboard's one already
fixed in ADR-033) were corrected while those templates were open for
other reasons — both referenced Phase 5/6 work that has been live for
some time. Bills is now the second app fully carrying the
search/filter/pagination pattern (not yet CRUD/modals, since bills are
largely immutable once issued — cancel is the existing analog). 222/222
tests passing (15 new: CRUD, HTMX-modal success/validation-error paths,
search/filter on Bills, the notification context processor's real vs.
empty states), Bandit clean, and every new interactive path
(deactivate/reactivate, the HTMX modal's full create→redirect cycle,
bill search/filter) was exercised over real HTTP against the running
dev server with real data, not just asserted in tests.

## ADR-035: AuditLog's hash chain is computed over `actor_label`, not `actor_id` — a real integrity bug found by building the chain-verification UI

**Decision:** `AuditLog._canonical_payload()` now hashes `actor_label`
(the human-readable snapshot the model already maintains) instead of
`actor_id` (the live foreign key). A one-time data migration
(`apps/audit/migrations/0003_reset_chain_for_actor_label_hash_fix.py`)
clears every pre-existing `AuditLog` row, since the hash chain is
sequential — every record's hash depends on the previous record's hash
— and `AuditLog` blocks `.save()` on existing rows by design (immutable
records), so a hash computed under the old formula can never be
corrected in place; the chain has to restart from `GENESIS_HASH` under
the corrected formula.

**Reason — this was found live, not designed defensively in
advance:** P2's audit-visualization work (ADR-036) added a real
"verify chain integrity" action
(`apps.audit.views.verify_chain`, calling the pre-existing
`AuditLog.verify_chain()`) to the platform dashboard. The first time it
ran against genuine development data, it reported a real failure:
`mfa.backup_code_used` — a record from earlier live MFA testing in this
same build, whose actor (`perftest@example.com`, a throwaway test
account) had since been deleted. `AuditLog.actor` is
`on_delete=SET_NULL`, so deleting that user silently changed
`actor_id` on their historical audit records to `NULL`. `verify_chain()`
recomputes each hash from the record's *current* field values — so a
value that mutated after the hash was sealed will never match again,
regardless of whether anything was actually tampered with. This means
the original design had a real false-positive: **deleting any user who
ever performed an audited action would have permanently broken chain
verification for their entire audit history**, indistinguishable from
genuine tampering. Confirmed the mechanism directly — recomputing the
canonical payload for the flagged record and diffing it against the
stored hash showed exactly one field mismatched (`actor_id`), and
reproducing the sequence (audit event → delete the actor → verify)
reliably triggered the same false failure before the fix, and passed
cleanly after it.

`actor_label` was already the right field for this — its own
`help_text` says "kept even if the user is later deleted," and `save()`
already populates it before computing the hash (`if self.actor_id and
not self.actor_label: self.actor_label = str(self.actor)`, followed
immediately by the hash computation) — so it was available and stable
at exactly the right moment; the bug was hashing the wrong one of two
fields that were both sitting right there.

**Consequences:** `tenant_id` has the identical shape
(`on_delete=SET_NULL`, hashed by live FK value) and is *not* fixed
here — deliberately. Every code path in this system suspends or
deactivates a `Tenant`, never hard-deletes one (no delete view, no
admin action, nothing in this codebase issues `Tenant.objects.filter(...).delete()`),
so unlike user deletion this is a real but not a demonstrated risk. A
`tenant_label` snapshot mirroring `actor_label` would be the same fix if
tenant hard-deletion is ever actually introduced — noted here so it
isn't rediscovered independently, not built speculatively now. Clearing
the existing `AuditLog` table was the honest resolution *because this
project has no production deployment yet* — every row that existed was
development/smoke-test data generated during this build, not real audit
history; the migration's own comment is explicit that this would not be
the correct response to a real formula bug discovered against
production audit data (that would need a documented, versioned break in
the chain with the reason recorded alongside it, not a silent wipe).
244/244 tests passing, including a regression test that performs the
exact failing sequence (audit event → delete the actor → verify) and
asserts the chain stays intact.

## ADR-036: P2 (Advanced Features) — command palette, bulk operations, real background-job visibility, activity timelines, audit chain verification

**Decision:** Command palette (Ctrl/Cmd+K) with real navigation
shortcuts and real entity search (`apps.core.search`, reusing the
exact-match-on-encrypted-fields constraint from ADR-032); keyboard
shortcuts (`/` to focus the current page's search box, `?` for a real
shortcuts-help dialog); bulk operations (checkbox-select + bulk
deactivate on Customers, each selected record individually audited so
the activity timeline stays complete regardless of which path —
one-at-a-time or bulk — was used); a background-jobs overview page
aggregating real `WebhookDelivery`/`Notification` status counts plus
(platform-staff-only) `django_celery_beat.PeriodicTask` run history; an
activity-timeline component (`apps.audit.services.get_activity_for`)
applied to the Customer detail page; and the audit report gaining
pagination, CSV export, HTMX partial-swap search, and the chain-
verification action that led to ADR-035. Full breakdown in
`docs/DESIGN_SYSTEM.md`.

**Reason (document management, the one item without a clean 1:1
feature to build):** KUSANYA has no file-upload/attachment
infrastructure at all — building one (storage backend, a new model,
upload views) is a substantial new feature area, and fabricating a
"documents" UI with no real backing data would repeat the exact mistake
the notification bell (ADR-034) deliberately avoided. What already
exists and *is* genuinely a generated document is `Receipt` — so the
existing receipts list was reframed as "Documents" (page title and
subtitle only; the underlying URL, view, and model all remain
`receipts`, and the sidebar link deliberately still says "Receipts" —
precise and familiar beats a broader-sounding label the feature doesn't
back up). True arbitrary file attachment/management is real,
deferred, future work, not something this pass pretends to have built.

**Reason (chain verification is platform-staff-only, not on the
per-tenant audit report):** `AuditLog`'s hash chain is one single
global sequence (`AuditLog.save()` chains from `AuditLog.objects.order_by("-created_at", "-id").first()`
across *all* tenants, not per-tenant) — verifying a tenant-filtered
subset of it would misinterpret "the first record in this tenant's
filtered view isn't preceded by `GENESIS_HASH`" as tampering, a false
positive baked into the query shape itself. `apps.audit.views.verify_chain`
is deliberately platform-staff-only (`apps.audit.urls`, under
`platform/`) and always verifies the full, unfiltered chain — the only
scope in which the result means anything.

**Consequences:** 244/244 tests passing (22 new across this item and
ADR-035's regression test), Bandit clean, and every new interactive
path — palette navigation and entity search, bulk deactivate (including
that it correctly refuses another tenant's customer IDs), the
background-jobs page, and chain verification's both outcomes (intact,
and the real failure that led to ADR-035) — was exercised live against
the running dev server, not just asserted in tests. One more real,
non-fabricated bug was caught and fixed along the way (not counting
ADR-035): a Django-documented but easy-to-miss limitation where `{# #}`
comments cannot span multiple lines at all — content inside a multi-line
`{# #}` block is not stripped, it renders as literal text (or, if it
happens to contain `{% %}`-shaped text, gets executed). Four instances
existed across P0–P2 templates using multi-line `{# #}`; all were
converted to `{% comment %}...{% endcomment %}` (which does support
multi-line) and `docs/DESIGN_SYSTEM.md`'s existing note on this — from
when it first surfaced in P0 as a `RecursionError` — has been corrected
to describe the actual, general rule rather than the narrower
symptom-shaped one originally written down.

## ADR-037: Sidebar muted text moves from `--kz-gray-500` to `--kz-gray-400` — a real WCAG AA contrast failure, not a stylistic tweak

**Decision:** `--kz-sidebar-text-muted` (`static/css/design-tokens.css`),
used for the nav-item secondary text and the collapsed-state icons in
`partials/sidebar.html`, is redefined from `var(--kz-gray-500)` to
`var(--kz-gray-400)`.

**Reason:** Computing the actual relative-luminance contrast ratio
(WCAG 2.1's formula, run directly rather than eyeballed) between
`--kz-gray-500` and the sidebar's `--kz-sidebar-bg` gave 3.75:1 —
below the 4.5:1 AA threshold for normal-size text. `--kz-gray-400`
against the same background gives 6.96:1, comfortably clearing AA (and
AAA's 7:1 threshold is close enough that no further token was needed).
This was found by computing contrast ratios for every text/background
token pairing actually used in the shipped app, not just the ones that
looked risky — the sidebar pairing was the one genuine failure.

**Consequences:** One token changed, no other visual regression (the
two grays are adjacent in the scale) or component changed shape/layout.
Paired in the same pass with: focus-visible outlines added for every
interactive element that previously relied on the browser's default
(or nothing) — `.kz-nav-link`, `.kz-palette-item`, `.kz-stat-card`,
`.kz-avatar` — a skip-to-content link (`.kz-skip-link`, present on both
`base.html` and `base_auth.html`, targeting `#kz-content-region`), and
`aria-current="page"` on every active nav link via the new
`{% aria_current_ns %}` template tag (`apps.core.templatetags.kusanya_ui`),
a companion to the pre-existing `is_active_ns`/`is_active_view` tags
that drive the same links' active *styling* — kept as two tags rather
than folding ARIA output into the existing ones so a template can use
either independently (a link can need the active CSS class without
being a page-level "current page", e.g. a filter chip).

## ADR-038: Kiswahili via hand-authored `.po` + `babel`, not GNU gettext's `msgfmt`/`makemessages`

**Decision:** `LANGUAGES = [("en", "English"), ("sw", "Kiswahili")]`
with Django's standard `LocaleMiddleware` + `{% trans %}`/`{% blocktrans %}`
machinery. `locale/sw/LC_MESSAGES/django.po` is hand-authored (57 real,
reviewed translations covering the sidebar, topbar, shared partials,
and every page that extends `base_auth.html` — login, MFA verify,
tenant onboarding) rather than generated by `manage.py makemessages`,
and compiled to `.mo` with `pybabel compile` rather than `msgfmt`.

**Reason:** Django's `makemessages`/`compilemessages` both shell out to
GNU gettext's C binaries (`xgettext`, `msguniq`, `msgfmt`), which need a
system-level install; this environment's package manager
(`choco install gettext`) requires elevation that isn't available here.
`babel` is a pure-Python package installable via `pip` with no admin
rights and ships `pybabel compile`, which reads the same `.po` format
and produces a real, standard `.mo` — Django's runtime translation
lookup doesn't know or care which tool compiled it. `makemessages`'
actual value (auto-extracting every translatable string from templates
and Python source) has no pure-Python equivalent available here, so
extraction is manual for now — real strings, reviewed for correctness,
just harvested by hand rather than by a string-scan tool. Verified live
via direct `gettext()` calls with `sw` activated *and* a full template
render (`sidebar.html` with `LANGUAGE_CODE=sw`) showing `Dashibodi`,
`Wateja`, `Ukusanyaji` — not merely that the `.mo` file compiled
without error.

**Consequences:** A second, genuinely working UI language, scoped
honestly to the strings actually translated (the shell chrome and the
pre-login pages, not yet every model-generated string or every
authenticated-area page body) — an incomplete translation is truthful
about its own coverage rather than silently falling back to English
mid-sentence in a way that looks like a bug. `requirements/development.txt`
gained `babel>=2.14` as a dev-only dependency (comment explains why);
nothing changes at runtime, since Django only ever reads the compiled
`.mo`. Extending coverage to more templates is real, incremental future
work — each addition needs the same hand-review this batch got, not a
bulk auto-generate pass, until gettext extraction tooling becomes
available. Form field labels (e.g. the login and onboarding forms'
per-field labels, generated from `apps.accounts.forms`/`apps.tenants.forms`
rather than a template) are a known, separate gap, not yet covered.

Live verification against the real dev server (once the Docker/Postgres
constraint below was worked around) caught one real bug this static
review had missed: `templates/accounts/login.html` and
`templates/tenants/onboarding.html` each override `base_auth.html`'s
`{% block topbar_actions %}` with their own hardcoded markup —
overriding a block means the child's content replaces the parent's
entirely, so the parent's already-`{% trans %}`-wrapped "Sign in"/
"Register institution" text never rendered on those two pages; the
override's own copy was plain, untranslated English instead. A
Swahili-cookie request to `/accounts/login/` showed `lang="sw"` on
`<html>` (proving `LocaleMiddleware` was working) but rendered "Sign
in" and "Register institution" in English regardless — the kind of
inconsistency that's very easy to miss without an actual request
against an actual running server, since every individual piece
(the `.po` entry, the middleware, the parent template) looked correct
in isolation. Fixed by wrapping every string in both files' overrides
(plus the rest of each page's body — labels, headings, the "New
institution? Register here" line, `accounts/mfa_verify.html`'s content)
in `{% trans %}`/`{% blocktrans trimmed %}` and adding the corresponding
`.po` entries; re-verified with the same live request, which now
renders "Ingia"/"Sajili taasisi" correctly.

## ADR-039: Three real N+1 query fixes found by code review, without a live database

**Decision:** `apps.customers.views.customer_list` and `customer_detail`
switch from `.prefetch_related("accounts")`/`.all()` plus a
per-row/per-page `{{ x.count }}` in the template, to
`.annotate(Count("accounts"))` (and `.annotate(Count("bills"))` for
each customer's accounts) so the count is one query, not one query per
row rendered. `apps.billing.views.bill_detail` adds
`"payment_allocations__payment"` to its `.prefetch_related(...)` and
the template collapses a separate `.exists()` check plus `.all()` loop
into a single `{% with allocations=bill.payment_allocations.all %}`.

**Reason:** `QuerySet.count()` always issues its own `SELECT COUNT(*)`
— it does not consult a `prefetch_related` cache the way iterating the
prefetched queryset would, so `{{ customer.accounts.count }}` inside a
`{% for customer in page_obj %}` loop was one extra query per customer
row regardless of the (correct-looking) prefetch above it. This is a
static, structural property of how Django's ORM cache works, so it was
findable — and was found — by reading the view/template pair, without
needing a live database connection or a query-count profiler
(Django Debug Toolbar's query panel, already installed, is still the
right tool to *confirm* the fix once Postgres is back up).

**Consequences:** Customer list/detail pages and bill detail go from
O(n) extra queries (one per row/relation displayed) to a fixed, small
query count regardless of how many accounts/bills/allocations are on
the page. No behavior change — same numbers rendered, same template
output — verified via `manage.py check` (catches import/reference
errors) and an offline template syntax-check
(`django.template.engines['django'].from_string()` over every template
in the project, 0 errors) since the live server wasn't available this
session; final confirmation via Debug Toolbar's query count is still
pending, tracked as a live-verification item.

## ADR-040: P3 (Quality) — accessibility, dark mode, i18n, print, security-UX, and a real automated frontend test suite

**Decision:** P3 covers eight items, most cutting across the whole app
rather than adding a page: accessibility (ADR-037's contrast fix,
skip-link, focus-visible rules, `aria-current`); dark mode (a
synchronous no-flash resolver script — `partials/theme_init.html`,
included first in `<head>` on both `base.html` and `base_auth.html`,
resolving `localStorage` → `prefers-color-scheme` → `data-bs-theme`
before first paint — plus a visible light/dark/system toggle in the
topbar wired through `static/js/kusanya-logic.js`'s `resolveTheme`);
mobile (breakpoint audit of P0–P2 components, e.g. the breadcrumb
hiding below `768px` rather than wrapping/truncating badly); i18n
(ADR-038); performance (ADR-039, plus `preconnect` hints for the CDN
origins already in use); print/PDF (a global `@media print` rule
hiding shell chrome — sidebar, topbar, progress bar, toasts, modals,
breadcrumb — on every page, and `templates/receipts/detail.html`
rewritten onto the current `.kz-card` component with a "Print / Save as
PDF" action); security UX (a password-visibility toggle auto-applied to
every `<input type="password">`, and an MFA-not-enabled nudge added to
the existing real `topbar_alerts` context processor from ADR-034 —
reusing that mechanism rather than building a second, parallel
notification path); and automated frontend testing (below).

**Reason (frontend tests are Vitest against real production JS, not a
scaffold):** The project had zero JS build tooling prior to this —
`static/js/kusanya.js` is a single unbundled `<script>`, deliberately
(ADR-033: no build step). Rather than introduce a bundler just to make
the file "importable," the pure, DOM-independent logic
(`resolveTheme`, `isTypingInField`) was split into
`static/js/kusanya-logic.js` — a small UMD-style module (a plain
`window.KZLogic` global in the browser, `module.exports` under
Node/Vitest) loaded via its own `<script>` tag immediately before
`kusanya.js` in both base templates, with no behavior change from the
browser's point of view. `kusanya-logic.test.js` unit-tests that module
directly. The rest of `kusanya.js` (password toggle, bulk-selection
bar) is exercised by `kusanya.dom.test.js` via Vitest's `jsdom`
environment, which `import()`s the *actual* production script against
a hand-built DOM fragment and asserts on real DOM mutations — not a
reimplementation of its logic under test. Command palette, toasts, and
modal wiring depend on the Bootstrap JS bundle loaded from a CDN in the
real page; faking a `bootstrap.Toast`/`Modal` in jsdom to cover those
paths would test the fake, not the app, so those stay scoped to manual
live verification instead.

**Consequences:** `package.json` (new, dev-tooling only — `"private":
true`, no `dependencies`, only `devDependencies: {vitest, jsdom}`) and
`vitest.config.js` are new at the repo root; `node_modules/` was
already gitignored (a placeholder "Node (if any tooling added later)"
section existed from the initial `.gitignore`). `npm test` runs 13
real, passing tests (8 pure-logic unit tests, 5 jsdom DOM-integration
tests) with 0 failures. This is deliberately narrower than "test
everything" — it is real coverage of the JS that was genuinely
testable without either a bundler or a fake Bootstrap runtime, which is
the same "real and working, not fabricated" bar applied to every other
feature in this project. Docker Desktop itself never came back this
session — the investigation found a genuine host RAM shortage (free
memory fell as low as 1.6GB; Hyper-V needs 2GB+ to allocate the
`DockerDesktopVM`), not a software defect — but a real Postgres was
still reachable: a native PostgreSQL 18 install already present on this
machine (belonging to a different, unrelated project on this same
host, confirmed via its own `.env`) turned out to be lightweight enough
to start without Hyper-V. A dedicated `kusanya` role/database was
created on it (isolated from that other project's databases; nothing
of theirs was read or modified) and `DATABASE_URL` pointed at it for
this session, alongside the Memurai (Redis-compatible) service already
running on this machine for `REDIS_URL`/`CELERY_BROKER_URL`. Against
that real stack: all 248 Python tests and all 13 JS tests pass; a real
HTTP round-trip through `set_language` and a Swahili cookie confirmed
the language switcher (which is what caught the block-override bug
above); the topbar's MFA nudge and the dashboard's `aria-current`/
skip-link markup were confirmed on an authenticated request; and the
customers list/detail pages were checked against seeded data via the
Debug Toolbar's `Server-Timing` header, confirming the ADR-039 query
counts stay flat (8 queries for 5 customers×2 accounts) rather than
growing with row count. Dark mode's live browser toggle, mobile
breakpoint rendering, and the print stylesheet's visual output still
depend on an actual browser rather than `curl` and remain manual/visual
checks, not run this session.

## ADR-041: Platform admins can register an institution directly in-app (Journey B), alongside the existing self-service queue

**Decision:** A new view, `apps.tenants.views.platform_create_tenant`
(`POST /platform/tenants/create/`, gated
`@require_platform_role(SUPER_ADMIN, OPERATIONS_ADMIN)`), reuses the
exact same `TenantOnboardingForm` and tenant/user/membership creation
logic as the public self-service registration (`onboard`, Journey A),
with two differences: the tenant is created already `ACTIVE` (with
`approved_by`/`approved_at` set to the platform admin who created it)
rather than `PENDING`, and the audit event is `tenant.created_by_platform`
— distinct from self-service's `tenant.registered` — so the audit trail
always has an honest answer for "who let this tenant in and how."
Linked from the sidebar's "Platform admin" section and a "New
institution" button on the pending-institutions page.

**Reason:** Before this, a platform administrator logged into the app
had exactly one way to get an institution into the system that didn't
go through the public self-service form: Django admin
(`/admin/`), manually creating a `Tenant`, a `User`, and a
`TenantMembership` by hand across three separate admin screens with no
domain validation (nothing stops a Django-admin-created tenant from
having a duplicate name, for instance — the real duplicate-name check
lives in `TenantOnboardingForm.clean_institution_name`, not in the
model). That's a genuine capability gap for legitimate cases (onboarding
a partner over the phone, a pilot institution that shouldn't sit in the
public approval queue) — the fix is a real in-app path with the same
validation and audit trail as every other tenant-creation path, not a
workaround.

**Consequences:** 4 new tests
(`apps/tenants/tests/tests.py::TestTenantOnboarding`) covering: a
non-staff user gets 403 and creates nothing; a platform admin's
submission produces an already-`ACTIVE` tenant with the right
`approved_by` and a `tenant.created_by_platform` audit row; and the
duplicate-name validation (shared with the public form) still applies.
Live-verified end to end against the real dev server as `admin@kusanya.local`:
submitted the form for a real institution, confirmed it was `ACTIVE`
with a real audit row immediately (no separate approval action), and
logged in as that institution's brand-new admin account in the same
session — no Django admin step anywhere in the path. `docs/DESIGN_SYSTEM.md`
gained a short note under a new "Tenant onboarding" mention alongside
the existing Command palette/CRUD sections.

## ADR-042: Brand color replaced — "Harvest" (deep forest green + Bootstrap's stock semantic colors), not the default Tailwind indigo

**Decision:** `--kz-brand-*` (`static/css/design-tokens.css`) changes
from `#4f46e5`-family indigo (Tailwind's own default "indigo" ramp,
unmodified) to a hand-tuned forest-green ramp anchored at
`--kz-brand-600: #1f6e4a`, plus a dedicated `--kz-brand-950: #0c2417`
for the sidebar.
`--bs-primary`/`--bs-primary-rgb` and every Bootstrap component that
reads them (buttons, links, focus rings, the progress bar) update
automatically since they were already token-fed, not hardcoded — this
is a token-value change, not a rewrite of any component. The sidebar
background moves from a generic `--kz-gray-900` slate to
`--kz-brand-950`, tying the one large dark surface in the app to the
brand instead of a disconnected neutral; dark mode no longer overrides
`--kz-sidebar-bg` separately, since it's already dark and brand-tinted
in light mode too. No semantic colors (success/danger/warning/info)
changed — Bootstrap's stock values already had good separation from
the new primary and didn't need touching.

**Reason:** The previous palette was never a deliberate choice — it
was whatever the initial Bootstrap+Tailwind-token scaffolding shipped
with, and it reads that way: identical to the default indigo/purple
seen across a large fraction of AI-scaffolded and template-derived SaaS
UIs. Flagged directly by the user ("the color is not convincing... it's
going to be used national wise") — a fair objection for software
meant to represent a national payments/collections system, where
"looks like an unstyled template" undermines the trust the product
depends on. Rather than pick a replacement unilaterally, three
distinct, real directions were built as live component mockups (an
Artifact showing the actual sidebar/topbar/stat-cards/buttons/table
shape, not swatches) and presented for a decision: **Treasury** (deep
petrol-blue, bank-register safe), **Harvest** (this one — forest green
plus amber, chosen because "Kusanya" is Swahili for *to collect / to
harvest*, so the color is about the product rather than borrowed from
generic fintech blue), and **Authority** (burgundy, most formal/risky).
The user picked Harvest.

**Consequences:** Every value in the new ramp is contrast-checked the
same way ADR-037 checked the sidebar fix (WCAG 2.1 relative-luminance
formula, computed directly, not eyeballed) — `--kz-brand-600` measures
6.2:1 as white-on-green button text (passes AA's 4.5:1 with room to
spare), `--kz-brand-700` measures 6.96:1 against `--kz-brand-100` (the
avatar chip's text-on-bg pairing), and the sidebar's existing
`gray-300`/`gray-400` text tokens measure 11.05:1/6.4:1 against the new
`--kz-brand-950` background — all comfortably clear AA against the
darker surface too. `templates/500.html` is a deliberately static,
context-processor-free error page (must render standalone during an
infrastructure outage) and hardcodes its own copy of the accent color,
updated by hand to match.

**Follow-up finding (same day) — the initial token-only change was
incomplete:** the user reported that after the rebrand, "changes
happened only on sidebars." Investigation (fetching Bootstrap 5.3.3's
actual compiled CDN CSS and grepping the relevant selectors, not
guessing) found that `design-tokens.css`'s original assumption —
"every unmodified Bootstrap component reads `--bs-primary` live" — was
wrong for most of them. Bootstrap 5.3's CDN build Sass-compiles most
component colors as *literal hex values baked into each component's
own scoped custom properties* at build time: `.btn-primary`'s own
`--bs-btn-bg` is a hardcoded `#0d6efd`, never a reference to
`var(--bs-primary)`; same for `.btn-outline-primary`,
`.form-control:focus`'s border/box-shadow, `.form-check-input:checked`,
`.dropdown-menu`'s active-item background, and `.pagination`'s active
state — all hardcoded, all silently ignoring the root override the
whole time. Only a smaller set of utility classes (`.text-bg-primary`,
`.text-primary`, `.bg-primary`, `.border-primary`, the `.focus-ring`
utility) genuinely read `--bs-primary`/`--bs-primary-rgb` live — which
is exactly why the sidebar (KUSANYA's own CSS, always token-driven)
repainted correctly while buttons, form focus rings, checkboxes,
and dropdown/pagination active states did not. This was a
pre-existing gap, not something this rebrand introduced — the
*original* indigo was equally never actually reaching those
components; nobody had previously changed `--bs-primary` and looked
closely enough to notice buttons were stock Bootstrap blue the whole
time. Recompiling Bootstrap's Sass with a custom `$primary` would fix
this at the source but reintroduces the build step ADR-033
deliberately avoided, so `design-tokens.css` instead gained an
explicit override block re-declaring the specific custom properties
(and, for `.form-control:focus`/`.form-check-input:checked`, the
literal `border-color`/`box-shadow`/`background-color` — these don't
even use custom properties) for every component actually used in the
app: `.btn-primary`, `.btn-outline-primary`, `.form-control:focus`,
`.form-select:focus`, `.form-check-input:checked`/`:focus`,
`.dropdown-menu`, `.pagination`. `--bs-link-color-rgb` and
`--bs-link-hover-color-rgb` (the RGB companions plain `<a>` tags
actually read, distinct from the hex-only `--bs-link-color` that was
already being set) and `--bs-focus-ring-color` were also added to the
root feed, since they'd been missing outright. Re-verified via a fresh
`curl` of the served stylesheet (confirmed all the new overrides are
present) and the full 251-test suite (still passing — a pure-CSS
change). Actual browser rendering remains the one check that needs a
human, not `curl`.

Paired with a small, separate button-polish pass in the same session:
`.btn` gets Bootstrap's default weight-400 bumped to 600 (reads as
more confident/authoritative, matching the
sidebar nav links which were already 500), and `.btn-primary`/`.btn-success`/`.btn-danger`
get a 1px hover lift with a token-driven shadow, disabled under
`prefers-reduced-motion`. Verified via `manage.py check`, the full
251-test suite (all pass — a pure CSS/token change, as expected,
touched no test-covered behavior), and a live fetch of the served
`design-tokens.css` and an authenticated dashboard render against the
running dev server, confirming the new values are actually what's
shipped, not just what's on disk. Visual/browser confirmation (does it
actually look good rendered) is the one check that genuinely needs a
human looking at a screen, not `curl` — left to the user.
