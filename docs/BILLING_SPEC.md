# Billing Specification

**Status: implemented (Phase 2), partially.** Code: `apps/billing/`. Bill
creation, line items, status state machine, and cancellation exist.
Payments, partial-payment tracking, and overpayment handling do not exist
yet (Phase 3/4) — see "What's not built yet" below.

## Bill status state machine

```text
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
**Implemented today:** `Bill.transition_to(new_status)` enforces the
diagram above via an explicit `ALLOWED_TRANSITIONS` table
(`apps/billing/models.py`) — an invalid jump (e.g. `DRAFT → PAID`,
skipping `ACTIVE`) raises `ValidationError` rather than silently
succeeding; tested in `apps/billing/tests/tests.py::TestBillStateMachine`.
The `PARTIALLY_PAID`/`PAID` transitions exist in the allowed-transitions
table but nothing calls them yet — there's no `Payment` model to drive
them until Phase 3.

## What a bill supports

**Implemented (Phase 2):** line items (`BillItem`, with `quantity` ×
`unit_amount` → `line_total`, and `Bill.total_amount` recomputed from
them via `recalculate_total()` — never hand-edited), due dates,
cancellation, free-form `metadata` JSON for sector-specific detail, and
idempotent creation by `external_reference` (see below). The portal's
quick-bill form (`apps/billing/views.py::bill_create`) creates
single-item bills; the underlying `get_or_create_bill()` service already
accepts an arbitrary items list — multi-item entry through the portal
UI itself isn't built yet, only through that service/admin.

**Not yet implemented:** taxes/levies, discounts, partial/full payment
application, overpayment handling, recurrence, and expiry sweeping — all
depend on the `Payment` domain (Phase 3) or a scheduler decision
(expiry), neither of which exist yet.

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
principle as control numbers (build spec section 14). **Implemented as**
`apps.billing.services.get_or_create_bill()`: a repeat call with a
matching `external_reference` returns the original bill **unchanged** —
the retried call's items are not applied, matching "did you already do
this," not "upsert." Tested in
`TestBillIdempotency::test_repeat_call_with_same_external_reference_returns_existing_unchanged`.
A losing race between two concurrent identical requests is resolved the
same way as control numbers: catch the `IntegrityError` from the
`UniqueConstraint` on `(tenant, external_reference)`, re-fetch, return
the winner.
