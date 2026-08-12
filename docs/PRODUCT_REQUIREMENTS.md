# Product Requirements

## Vision

KUSANYA is universal digital collections infrastructure. It sits between
an institution's existing business system (ERP, POS, hospital system,
hotel system, school system, accounting software) and licensed payment
infrastructure:

```
Institution ERP/POS
        │  API
        ▼
     KUSANYA
        │  Billing · Control Numbers · Payment Orchestration
        │  Ledger · Reconciliation · Notifications · Reporting
        ▼
Licensed Payment Provider(s)
        │  Bank · Mobile Money · other legally supported channels
```

KUSANYA is **sector-neutral**. Schools are one tenant type among many:
education, healthcare, retail, hospitality, property management,
professional services, NGOs, religious organizations, training
institutions, membership organizations, utilities, associations, and
other legitimate organizations that issue bills and collect payments. See
[MULTI_TENANCY.md](MULTI_TENANCY.md) for how sector information is
modeled without leaking into core billing/payment logic.

## Universal data model

Core entities are generic, never sector-specific:

`Tenant`, `Customer`, `CustomerAccount`, `Bill`, `BillItem`,
`RevenueSource`, `ControlNumber`, `Payment`, `PaymentAllocation`,
`PaymentProvider`, `PaymentChannel`, `CollectionAccount`, `Settlement`,
`SettlementBatch`, `LedgerEntry`, `PlatformRevenue`, `Notification`,
`WebhookEvent`, `AuditLog`.

Sector-specific detail (student ID, patient ID, lease ID, reservation ID,
...) is stored in a `metadata` JSON field on the relevant record, never as
bespoke columns on core models. The billing/payment engine never branches
behavior on sector.

## Development phases

Phase 1 (**this build**) is the foundation only: project scaffolding,
Django/PostgreSQL/Redis/Celery/Docker wiring, base templates,
authentication, multi-tenancy, RBAC, and audit logging. No billing or
payment code exists yet — see [../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md)
ADR-005 for why later-phase apps aren't pre-scaffolded.

| Phase | Scope |
|---|---|
| 1 | **Done.** Foundation: Django, Postgres, Redis, Celery, Docker, auth, tenancy, RBAC, audit |
| 2 | **Done.** Customer, Account, Billing, Control Number |
| 3 | **Done.** Payment domain, provider abstraction, mock provider, payment lifecycle, idempotency, webhooks |
| 4 | **Done.** Ledger, Revenue, Reconciliation, Settlement |
| 5 | **Done.** Notifications, Receipts, Reports |
| 6 | **Done.** External API, API keys, webhooks, OpenAPI docs |
| 7 | Security hardening, full test coverage, monitoring, production prep |

## Core user journeys (target)

- **A — Institution onboarding:** registration → platform approval →
  tenant → admin user → configuration. Implemented in Phase 1
  (`apps.tenants.views.onboard` / `approve_tenant`), minus the
  "configuration" step, which depends on Phase 2+ domain settings.
- **B — Create bill:** customer → account → bill → control number →
  creation fee. **Implemented except the fee** (Phase 2:
  `apps.customers.services`, `apps.billing.services.get_or_create_bill`,
  `apps.control_numbers.services.get_or_create_for_bill`, wired together
  in `apps.billing.views.bill_create`, which issues the bill and requests
  its control number in one flow — verified end-to-end over real HTTP
  during Phase 2 development). The TZS 50 creation fee itself is Phase 4
  (revenue engine) — the `created`/`reused` distinction it will key off
  is already correct and tested.
- **C — Reuse control number:** existing account → request control number
  → existing one returned → no second creation fee. **Fully implemented,
  fee included** (`get_or_create_for_bill`/`get_or_create_for_account`
  charges via `apps.revenue.services` only on genuine creation — see
  [CONTROL_NUMBER_SPEC.md](CONTROL_NUMBER_SPEC.md) and
  [PRICING_MODEL.md](PRICING_MODEL.md), including the build spec's own
  worked example reproduced exactly).
- **D — Payment:** customer → provider → callback → successful → ledger →
  balance update → platform fee → notification → receipt. **Fully
  implemented, end to end** (Phase 3/4/5: `apps.payments.services`,
  `apps.ledger`, `apps.revenue`, `apps.notifications`, `apps.receipts` —
  a payment posts `PAYMENT_RECEIVED`/`INSTITUTION_ENTITLEMENT`/
  `PLATFORM_PAYMENT_FEE` ledger entries, the TZS 50 fee, a webhook, a
  templated email + SMS notification, and an automatically generated
  receipt, in that order, all verified in one live run against real
  infrastructure).
- **E — Partial payments:** multiple payments against one bill until
  fully paid. **Implemented** — `apps.payments.services._allocate_to_bill`
  transitions `ACTIVE → PARTIALLY_PAID → PAID` as successive payments are
  allocated; tested with three sequential payments fully paying a bill.
- **F — Provider failure:** timeout → UNKNOWN → reconciliation → final
  status. **Fully implemented** (Phase 3/4: timeout → UNKNOWN →
  `query_payment()` → resolved, plus Phase 4's `run_reconciliation()` as
  the scheduled-on-demand backstop that resolves any UNKNOWN payment left
  over and flags provider/internal status drift as an exception rather
  than silently correcting it) — see
  [PAYMENT_LIFECYCLE.md](PAYMENT_LIFECYCLE.md) and
  [RECONCILIATION_SPEC.md](RECONCILIATION_SPEC.md). Reconciliation runs
  on demand (a portal button / platform action), not yet on an automatic
  Celery beat schedule.
- **G — ERP integration:** external system authenticates, creates a bill,
  gets a control number, receives a webhook. **Fully implemented** —
  verified live: a real API credential, created through the tenant
  portal, drove `curl` requests through `POST /api/v1/customers/` →
  `/accounts/` → `/bills/` → `/bills/{id}/control-number/` →
  `/payments/`, ending with the bill's status flipping to `paid` and a
  receipt generated, entirely over HTTP with no portal session involved.
  "Receives a webhook" was already real since Phase 3. See
  [API_ARCHITECTURE.md](API_ARCHITECTURE.md).

## Non-goals for Phase 1 (explicitly out of scope, then — none remain as of Phase 6)

Billing, control numbers, payments, provider adapters, ledger, revenue,
reconciliation, settlement, notifications, receipts, reports, and the
external REST API. Any UI element that might imply these exist was
labeled "Not yet implemented" rather than showing placeholder/fake data
(build spec section 44). As of Phase 6, every domain listed in this
document's vision (section 1 of the build spec) is implemented and
tested. What remains out of scope is Phase 7's hardening work —
production-grade rate limiting/monitoring, full security review, and a
real (non-mock) payment provider once one is licensed and contracted —
see [SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md) and
[compliance/REGULATORY_ASSUMPTIONS.md](compliance/REGULATORY_ASSUMPTIONS.md)
for what that would actually require.
