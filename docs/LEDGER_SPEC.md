# Financial Ledger Specification

**Status: implemented (Phase 4).** Code: `apps/ledger/`. This document
specifies the ledger design — not "a payments table," an actual auditable
ledger (build spec section 16) — and records what's actually posted.

## Every `LedgerEntry` carries

UUID id, `created_at` timestamp, `reference`, `currency`, `amount`
(`Decimal`, never `float` — see
[../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md) ADR-003),
`entry_type`, a generic `source` (the `Payment`/`ControlNumber`/etc. this
entry is about), `account` (destination/account classification —
`CUSTOMER`/`INSTITUTION`/`PLATFORM`/`PROVIDER`/`SUSPENSE`),
`correlation_id`, and `related_entry` (linking a compensating entry back
to what it corrects).

## Event types implemented

`BILL_AMOUNT` (not yet posted — see below), `PAYMENT_RECEIVED`,
`INSTITUTION_ENTITLEMENT`, `PLATFORM_CONTROL_NUMBER_FEE`,
`PLATFORM_PAYMENT_FEE`, `PROVIDER_FEE` (field exists, always 0 — no real
provider charges fees yet), `REFUND`, `REVERSAL`, `SETTLEMENT` (not yet
posted as its own entry — see below), `ADJUSTMENT`. See
[MONEY_FLOW.md](MONEY_FLOW.md) for why these are always separately
identifiable rather than netted together — and see that document's
worked example, now reproduced exactly by the implementation: a 500,000
TZS payment posts `PAYMENT_RECEIVED` (500,000, account=CUSTOMER),
`INSTITUTION_ENTITLEMENT` (500,000, account=INSTITUTION), and
`PLATFORM_PAYMENT_FEE` (50, account=PLATFORM) as three separate rows —
verified via a full run-through against real PostgreSQL during Phase 4
development (see the Phase 4 development report).

**Not yet posted:** a `BILL_AMOUNT` entry at bill creation time (the bill
total is currently only recorded on `Bill.total_amount`, not mirrored
into the ledger) and a dedicated `SETTLEMENT` entry per batch (settlement
amounts are fully computed and recorded on `SettlementBatch` itself —
see [SETTLEMENT_SPEC.md](SETTLEMENT_SPEC.md) — just not additionally
mirrored as ledger rows yet). Neither gap affects any currently
implemented correctness guarantee; both are natural additions once a
reporting need specifically requires them in ledger form.

## Immutability — implemented

`apps.ledger.models.LedgerEntry.save()` raises `LedgerEntryImmutableError`
on any attempt to update an existing row; `.delete()` always raises.
Corrections are compensating entries — `apps.ledger.services.post_compensating_entry()`
creates a new row linked via `related_entry`, never touching the
original. This mirrors the pattern already implemented for the audit log
(`apps.audit.AuditLog` — see
[../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md) ADR-006),
deliberately *without* a hash chain — the audit log already provides
platform-wide tamper-evidence; a second, per-app chain would be
redundant, not additional safety. Tested:
`apps/ledger/tests/tests.py::TestLedgerImmutability`.

## Relationship to the audit log and to revenue events

Three related-but-distinct records, each with its own reason to exist:

- **`AuditLog`** (Phase 1): "who did what, when, from where" — logins,
  config changes, approvals, *and* financial events alike.
- **`LedgerEntry`** (this doc): "what is the exact financial position" —
  amounts, accounts, currency; every ledger-affecting action also
  produces an audit event, but not every audit event produces a ledger
  entry (a login doesn't).
- **`RevenueEvent`** (`apps.revenue` — see
  [PRICING_MODEL.md](PRICING_MODEL.md)): specifically KUSANYA's own fee
  events, including the *zero-fee* ones (`CONTROL_NUMBER_REUSED`,
  `PAYMENT_FAILED`, `PAYMENT_DUPLICATE`) that have no ledger entry at all
  because a zero-value ledger line has no financial meaning. Every
  non-zero `RevenueEvent` links to the `LedgerEntry` it corresponds to.

## Outstanding balance is always computed, never stored-and-edited

**Implemented exactly as specified.** `Bill.balance` and `Bill.amount_paid`
(`apps/billing/models.py`) are computed properties, summing
`PaymentAllocation` rows at query time — never a field an operator or API
client can directly overwrite. The `Payment`/`PaymentAllocation` rows
themselves are what the ledger's `PAYMENT_RECEIVED`/
`INSTITUTION_ENTITLEMENT` entries are posted from, so the ledger and the
bill balance can never independently drift out of sync — they're both
reflections of the same underlying payment records.
