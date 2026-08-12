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
| 3 | Payment domain, provider abstraction, mock provider, payment lifecycle, idempotency, webhooks |
| 4 | Ledger, Revenue, Reconciliation, Settlement |
| 5 | Notifications, Receipts, Reports |
| 6 | External API, API keys, webhooks, OpenAPI docs |
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
  → existing one returned → no second creation fee. **Implemented**
  (`get_or_create_for_bill`/`get_or_create_for_account` — see
  [CONTROL_NUMBER_SPEC.md](CONTROL_NUMBER_SPEC.md) and
  [PRICING_MODEL.md](PRICING_MODEL.md) for the rule verified). Fee
  charging itself is Phase 4.
- **D — Payment:** customer → provider → callback → successful → ledger →
  balance update → platform fee → notification → receipt. Not implemented
  (Phase 3/4/5).
- **E — Partial payments:** multiple payments against one bill until
  fully paid. Not implemented — depends on the `Payment` model (Phase 3).
  The `Bill` state machine already has `PARTIALLY_PAID`/`PAID` states
  ready for Phase 3 to drive.
- **F — Provider failure:** timeout → UNKNOWN → reconciliation → final
  status. Not implemented (Phase 3/4) — see
  [PAYMENT_LIFECYCLE.md](PAYMENT_LIFECYCLE.md).
- **G — ERP integration:** external system authenticates, creates a bill,
  gets a control number, receives a webhook. Not implemented (Phase 6).

## Non-goals for Phase 1 (explicitly out of scope, then)

Billing, control numbers, payments, provider adapters, ledger,
reconciliation, settlement, notifications, receipts, reports, and the
external REST API. Any UI element that might imply these exist was
labeled "Not yet implemented" rather than showing placeholder/fake data
(build spec section 44). Billing and control numbers are now built
(Phase 2, above) — payments, provider adapters, ledger, reconciliation,
settlement, notifications, receipts, reports, and the API remain
out of scope until their respective phases.
