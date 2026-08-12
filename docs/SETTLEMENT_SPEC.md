# Settlement Specification

**Status: not yet implemented** (Phase 4). Settlement is modeled as a
separate domain from payments and the ledger — it's the step where
collected funds actually move to an institution's own account, and it is
the domain most directly bounded by KUSANYA's regulatory posture. Read
[compliance/REGULATORY_ASSUMPTIONS.md](compliance/REGULATORY_ASSUMPTIONS.md)
before implementing this.

## What a settlement batch tracks

Batch identifier, provider, institution (tenant), gross amount, fees
(platform + provider, itemized — see [MONEY_FLOW.md](MONEY_FLOW.md)), net
amount, settlement reference, settlement date, and status.

## The regulatory boundary this domain must respect

KUSANYA's settlement architecture assumes funds move from the licensed
provider/bank directly (or via a licensed arrangement) to the
institution's own account — it does **not** assume KUSANYA itself is
legally entitled to hold or redistribute merchant/customer funds. The
`Settlement`/`SettlementBatch` models record and reconcile that movement;
they must not be designed in a way that implies KUSANYA is a party
holding funds in transit unless a specific licensed arrangement (bank
partnership, e-money license, etc.) establishes that role — see build
spec section 18 and section 2.

## Status states

Settlement batches move through states analogous to reconciliation
(pending → processing → completed → exception) — the exact state machine
is a Phase 4 design task; this document records the constraint (never
assume custody) that any such state machine must respect, not the final
state list.
