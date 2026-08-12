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
