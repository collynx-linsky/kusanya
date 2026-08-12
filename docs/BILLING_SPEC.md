# Billing Specification

**Status: not yet implemented** (Phase 2). This document specifies the
design the billing engine must follow.

## Bill status state machine

```
DRAFT → ACTIVE → PARTIALLY_PAID → PAID
           │           │
           ├──────► EXPIRED
           ├──────► CANCELLED
           └──────► DISPUTED
```

- `DRAFT` — not yet issued to the customer; no control number required
  yet, can be freely edited.
- `ACTIVE` — issued, has (or can request) a control number, awaiting
  payment.
- `PARTIALLY_PAID` — at least one payment recorded, balance remaining.
- `PAID` — balance is zero (subject to the tenant's overpayment rules —
  see below).
- `EXPIRED` — passed its due date without being paid, per tenant
  configuration of whether unpaid bills expire.
- `CANCELLED` — voided before payment; no payment fee event is generated
  for a cancelled bill (see [PRICING_MODEL.md](PRICING_MODEL.md)).
- `DISPUTED` — flagged for manual review; blocks certain automatic
  transitions (exact rules TBD in Phase 2 design).

Bill status is derived from the underlying ledger (sum of allocated
payments vs. bill total), never hand-set to `PAID` by application code
without that sum actually reaching the bill total — this mirrors the
control-number balance rule in [CONTROL_NUMBER_SPEC.md](CONTROL_NUMBER_SPEC.md).

## What a bill supports

Line items (`BillItem`), taxes/levies where configured by the tenant and
legally applicable, discounts, due dates, partial payments, full
payments, overpayments (subject to configurable tenant rules — some
tenants may want overpayments rejected, others may want them credited to
the customer's account balance), cancellation, expiry, recurrence,
free-form metadata for sector-specific detail, and an external reference
so ERP-originated bills can be looked up by the caller's own ID
(idempotency — see build spec section 14's `INV-2026-00125` example).

## Sector neutrality

`Bill`/`BillItem` never has sector-specific columns (no `student_id`,
`patient_id`, etc. as real fields) — that detail lives in the bill's
`metadata` JSON field. The billing engine's logic (issue → apply payment →
recompute balance → transition status) is identical regardless of what
generated the bill. See
[PRODUCT_REQUIREMENTS.md#universal-data-model](PRODUCT_REQUIREMENTS.md#universal-data-model).

## Idempotent bill creation

An ERP retrying a "create bill" call with the same `external_reference`
must get back the existing bill, not a duplicate — same idempotency
principle as control numbers (build spec section 14).
