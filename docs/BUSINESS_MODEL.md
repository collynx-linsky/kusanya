# Business Model

**Status: not yet implemented.** This document specifies the intended
model for the revenue engine to be built in Phase 4. Nothing described
here is charged or calculated by the current codebase.

## Model

Transaction-based. There is **no mandatory monthly subscription** in the
initial business model — KUSANYA earns revenue only when it does
something billable: creates a genuinely new control number, or processes
a successful payment.

Two fee events:

1. **New control number creation** — TZS 50, charged only when a control
   number is genuinely newly created, never on retrieval of an existing
   one.
2. **Successful payment** — TZS 50, charged per successful payment, so a
   control number paid in five installments generates five payment fees.

See [PRICING_MODEL.md](PRICING_MODEL.md) for the exact rule set and worked
examples, and [MONEY_FLOW.md](MONEY_FLOW.md) for how gross collections,
institution entitlement, provider fees, and KUSANYA's fee are kept
separately identifiable end to end.

## Why transaction-based, not subscription

An institution should be able to try KUSANYA and pay only for what it
actually uses — a control number that's created but never paid against
costs the institution nothing beyond the one-time TZS 50 creation fee.
This aligns KUSANYA's incentives with actually helping institutions
collect money, not with seat-count sales.

## Not decided / explicitly out of scope here

Tiered pricing, volume discounts, provider-specific fee pass-through
beyond the provider's own charge, currency-specific fee schedules for
non-TZS tenants, and any subscription add-on tier. These would each need
their own product decision and are not assumed by the architecture — the
revenue engine (Phase 4) is built so fee amounts are configuration, not
hard-coded constants scattered through billing/payment code (build spec
principle 10).
