# Pricing Model

**Status: implemented (Phase 4).** Code: `apps/revenue/`. The fee
schedule is defined in exactly one place —
`apps.revenue.services.CONTROL_NUMBER_CREATION_FEE` and
`PAYMENT_SUCCESS_FEE` — never scattered across billing/payment/
control-number code (build spec principle 10). This document records the
rule set and confirms it's satisfied, including by the build spec's own
worked example, reproduced exactly.

## Fee schedule — implemented as `apps.revenue.models.RevenueEventType`

| Event | Fee |
|---|---|
| `CONTROL_NUMBER_CREATED` (genuinely new) | TZS 50 |
| `CONTROL_NUMBER_REUSED` | TZS 0 |
| `PAYMENT_SUCCESSFUL` | TZS 50 |
| `PAYMENT_FAILED` | TZS 0 |
| `PAYMENT_REVERSED` | see "Reversal/refund" below |
| `PAYMENT_REFUNDED` | see "Reversal/refund" below |
| `PAYMENT_DUPLICATE` (duplicate webhook/callback) | TZS 0 |
| Cancelled bill | no payment fee is possible — a cancelled bill's control number was either never paid, or cancellation itself doesn't reverse a payment |

Every row above — including the zero-fee ones — is recorded as a
`RevenueEvent`, not just the charged ones; see
[LEDGER_SPEC.md](LEDGER_SPEC.md) for why (queryable metrics like "how
often are control numbers reused" without needing a fee).

## The control-number-reuse rule — implemented and verified exactly

**Worked example** (build spec section 3), reproduced against real
PostgreSQL during Phase 4 development:

```text
Request 1: create control number         → new                → TZS 50
Request 2: request same control number   → existing returned  → TZS 0
Request 3: request same control number   → existing returned  → TZS 0
Payment 1 successful                     →                     → TZS 50
Payment 2 successful (same control no.)  →                     → TZS 50
```

The build spec's own five-payment variant — one new control number + 5
successful payments = TZS 50 + 5×TZS 50 = **TZS 300** — is exactly what
`apps/revenue/tests/tests.py::TestBuildSpecWorkedExample` asserts, and
what a live run against real PostgreSQL produced: `TOTAL PLATFORM
REVENUE: 300.00`.

**Implemented as:** `apps.control_numbers.services.get_or_create_for_bill`/
`_for_account` call `apps.revenue.services.record_control_number_created`
only on the branch where a control number was genuinely just created,
and `record_control_number_reused` (TZS 0, no ledger entry) on every
retrieval-of-existing branch — the fee event is a direct consequence of
that service's own idempotency decision, never inferred after the fact.

## Reversal / refund accounting treatment — implemented, configurable per tenant

`Tenant.fee_refund_policy` (`CLAWBACK` default, or `RETAIN`) — build spec
section 4's required configurability point, not a hard-coded choice.
`apps.revenue.services._compensate()`:

- **`CLAWBACK`** (default): posts a `PAYMENT_REVERSED`/`PAYMENT_REFUNDED`
  `RevenueEvent` for `-50` (negating the original fee) plus a
  compensating `LedgerEntry` linked via `related_entry` — the original
  `PAYMENT_SUCCESSFUL` event and its ledger entry are **never** touched
  or deleted, exactly per build spec section 4's "use immutable financial
  events and compensating entries." Net revenue from that payment becomes
  zero, but both the +50 and −50 events remain visible forever.
- **`RETAIN`**: posts the same event type at amount 0 — the fee stays
  charged, recorded for audit completeness, no ledger entry since there's
  no financial effect to record.

Both branches tested explicitly:
`TestReversalRefundAccountingTreatment::test_clawback_policy_creates_negative_compensating_event`
and `test_retain_policy_keeps_the_fee_on_refund`.

## Immutability

`RevenueEvent.save()`/`.delete()` both raise
`RevenueEventImmutableError` after creation — same enforcement pattern as
`AuditLog` (ADR-006) and `LedgerEntry`. Tested.

## Currency

Fees are denominated in each tenant's `default_currency` (TZS by default
— see [MONEY_FLOW.md](MONEY_FLOW.md)). No TZS-to-other-currency
conversion is assumed or implemented; a tenant using a different currency
would need its own fee schedule, which isn't built (every tenant in
Phase 4 uses the same fee amounts regardless of currency — a gap worth
revisiting before onboarding a non-TZS tenant with real payments).

## Tests — build spec section 34's fee-related scenarios, all passing

Create control number once → fee charged once ✅; request same control
number three times → fee charged once total ✅; five successful payments
on one control number → five payment fees (TZS 250) ✅; failed payment →
no fee ✅; duplicate webhook for the same payment → no second fee ✅
(tested at both the payment-callback level and confirmed the revenue
event count matches); reversal/refund → compensating event, original
never deleted ✅, both accounting-treatment policies tested. All 22 new
Phase 4 tests across `apps/ledger/tests/`, `apps/revenue/tests/`,
`apps/reconciliation/tests/`, `apps/settlement/tests/` pass (109/109
total across the whole suite), against real PostgreSQL.
