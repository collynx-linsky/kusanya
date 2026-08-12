# Settlement Specification

**Status: implemented (Phase 4).** Code: `apps/settlement/`. Settlement
is modeled as a separate domain from payments and the ledger — it's the
step where collected funds actually move to an institution's own
account, and it is the domain most directly bounded by KUSANYA's
regulatory posture. Read
[compliance/REGULATORY_ASSUMPTIONS.md](compliance/REGULATORY_ASSUMPTIONS.md)
before extending this domain further.

## What a `SettlementBatch` tracks — implemented exactly as specified

Batch reference (auto-generated, unique per tenant), provider, tenant
(institution), `period_start`/`period_end`, `gross_amount`,
`platform_fee_total`, `provider_fee_total` (always 0 today — no real
provider charges fees yet; the field exists for when one does),
`net_amount` (= gross − platform fee − provider fee), currency,
`external_settlement_reference` (the provider/bank's own reference,
entered only when marking a batch completed), and status.

## The regulatory boundary this domain respects

**Implemented as:** `apps.settlement.services.generate_settlement_batch()`
only ever *computes and records* what a batch of settled payments amounts
to — it moves no money. `mark_settlement_completed()` — gated to platform
Finance/Super Admin roles, never available to tenant users — represents a
human recording that the licensed provider/bank has *already* confirmed
the actual transfer; the function's docstring and the portal's own
confirmation copy both say this explicitly ("only do this once the
licensed provider/bank has actually confirmed the funds transfer... —
KUSANYA does not move these funds itself"). No code path in this
codebase debits or credits any real account. See build spec section 18
and section 2.

## Double-settlement prevention — implemented at the database level

`Payment.settlement_batch` (nullable FK, added in Phase 4) is set exactly
once, inside `generate_settlement_batch()`'s `transaction.atomic()` block
using `select_for_update()` on the candidate payments — a payment already
claimed by a batch (`settlement_batch__isnull=False`) is never selected by
a later batch generation, and the `select_for_update` lock closes the race
between two concurrent batch-generation calls for the same tenant/period.
Tested directly: generating a batch twice for the identical period
includes the same payments only in the first batch, zero in the second —
verified both in `apps/settlement/tests/tests.py` and manually against
real PostgreSQL (5 payments settled once; a second generation for the
same period returned 0 payments).

## Status states — implemented

```text
PENDING → COMPLETED
PENDING → EXCEPTION  (not yet triggered by any code path — reserved for
                       a future integration that can detect a settlement
                       discrepancy automatically)
```

## What's not built yet

Automatic settlement scheduling (batches are generated on demand today,
by a platform admin choosing a tenant/provider/period — no Celery beat
job runs this automatically); multi-provider fee schedules (moot with
only the mock provider, which charges nothing); a `SETTLEMENT`
`LedgerEntry` per batch (the amounts are fully recorded on
`SettlementBatch` itself; not yet additionally mirrored into the ledger —
see [LEDGER_SPEC.md](LEDGER_SPEC.md)).
