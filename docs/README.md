# KUSANYA Documentation

KUSANYA is digital collections and payment infrastructure: institutions
create bills, issue persistent control numbers, accept payments through
licensed payment providers, and get an auditable ledger, reconciliation,
and reporting. It is explicitly **not** a school-specific system — see
[PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md).

**Read this first if you're new:** [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md) →
[MULTI_TENANCY.md](MULTI_TENANCY.md) → [../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md).

**Read this first if you're evaluating regulatory posture:**
[compliance/REGULATORY_ASSUMPTIONS.md](compliance/REGULATORY_ASSUMPTIONS.md).

## Index

| Document | Covers |
|---|---|
| [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md) | Vision, universal data model, phased roadmap |
| [BUSINESS_MODEL.md](BUSINESS_MODEL.md) | Transaction-based revenue model |
| [PRICING_MODEL.md](PRICING_MODEL.md) | Exact fee rules (control number / payment fees) |
| [MONEY_FLOW.md](MONEY_FLOW.md) | Who owes whom, at each step of a payment |
| [CONTROL_NUMBER_SPEC.md](CONTROL_NUMBER_SPEC.md) | Persistent control number engine |
| [BILLING_SPEC.md](BILLING_SPEC.md) | Bill lifecycle and states |
| [PAYMENT_LIFECYCLE.md](PAYMENT_LIFECYCLE.md) | Payment state machine, UNKNOWN handling |
| [PAYMENT_PROVIDER_ARCHITECTURE.md](PAYMENT_PROVIDER_ARCHITECTURE.md) | Provider adapter abstraction |
| [LEDGER_SPEC.md](LEDGER_SPEC.md) | Immutable financial ledger |
| [RECONCILIATION_SPEC.md](RECONCILIATION_SPEC.md) | Cross-system matching |
| [SETTLEMENT_SPEC.md](SETTLEMENT_SPEC.md) | Settlement batches |
| [NOTIFICATION_SPEC.md](NOTIFICATION_SPEC.md) | Templated multi-channel notifications |
| [MULTI_TENANCY.md](MULTI_TENANCY.md) | Tenant isolation guarantees |
| [RBAC.md](RBAC.md) | Platform and tenant roles |
| [SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md) | Security controls, honest gaps |
| [API_ARCHITECTURE.md](API_ARCHITECTURE.md) | External REST API design (Phase 6) |
| [DATABASE_ARCHITECTURE.md](DATABASE_ARCHITECTURE.md) | PostgreSQL conventions |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Environments, Docker, production topology |
| [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md) | Backup/recovery posture |
| [TESTING.md](TESTING.md) | Test strategy and how to run tests |
| [COMPLIANCE_ASSUMPTIONS.md](COMPLIANCE_ASSUMPTIONS.md) | Summary — see compliance/ for detail |
| [compliance/REGULATORY_ASSUMPTIONS.md](compliance/REGULATORY_ASSUMPTIONS.md) | Full regulatory-boundary documentation |

## What exists today (Phase 1 + 2)

**Phase 1:** identity (`apps.users`), authentication (`apps.accounts`),
multi-tenancy and RBAC (`apps.tenants`), organizational sub-structure
(`apps.organizations`), and the hash-chained audit log (`apps.audit`).

**Phase 2:** customers and billing relationships (`apps.customers`),
bills with an enforced status state machine (`apps.billing`), and the
persistent control-number engine with its create-once/reuse-many
guarantee (`apps.control_numbers`) — all idempotent by
`external_reference`, all tenant-isolated, all tested against real
PostgreSQL and (for the core control-number guarantee) verified over
real HTTP end to end.

Payments, the provider abstraction, the ledger, reconciliation,
settlement, notifications, receipts, reports, and the external API do not
exist yet (Phase 3–6). Every document in this folder describes the
**target** design for its domain; where that domain isn't built yet, the
document says so rather than implying it's live.
