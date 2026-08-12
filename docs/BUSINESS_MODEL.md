# Business Model

**Status: implemented (Phase 4).** Code: `apps/revenue/`. Both fee events
described below are live and verified — see
[PRICING_MODEL.md](PRICING_MODEL.md) for the exact rules and test
evidence.

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
revenue engine (`apps.revenue.services`) defines both fee amounts as two
module-level constants, not hard-coded literals scattered through
billing/payment code (build spec principle 10), so a future pricing
change is a one-line edit, not a code hunt.
