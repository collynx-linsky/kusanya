# Financial Ledger Specification

**Status: not yet implemented** (Phase 4). This document specifies the
ledger design — not "a payments table," an actual auditable ledger (build
spec section 16).

## Every `LedgerEntry` carries

Unique ID, timestamp, reference, currency, amount (`Decimal`, never
`float` — see [../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md)
ADR-003), event type, source, destination/account classification, status,
correlation ID, and an audit trail link.

## Event types tracked (non-exhaustive, extended as needed)

Bill amount, payment amount, payment allocation, institution entitlement,
platform control-number fee, platform payment fee, provider fee, refund,
reversal, settlement, adjustment. See [MONEY_FLOW.md](MONEY_FLOW.md) for
why these must always be separately identifiable rather than netted
together.

## Immutability

Settled financial events are never modified or deleted. Corrections are
compensating entries — a new `LedgerEntry` that offsets a prior one,
leaving both visible — never an UPDATE or DELETE against a settled row.
This mirrors the pattern already implemented for the audit log
(`apps.audit.AuditLog` — see [../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md)
ADR-006) and must be enforced the same way: block mutation/deletion at
the model layer, not just by convention.

## Relationship to the audit log

The ledger and the audit log are not the same thing and should not be
merged: the audit log answers "who did what, when, from where" across the
whole platform (logins, config changes, approvals, financial events
alike); the ledger answers "what is the exact, always-reconcilable
financial position of every account, tenant, and the platform itself."
Every ledger-affecting action should also produce an audit event, but not
every audit event produces a ledger entry.

## Outstanding balance is always computed, never stored-and-edited

A bill's or control number's outstanding balance is `bill_total - SUM(
allocated payments)`, computed from ledger rows at query time (or
maintained as a cached, ledger-derived value that is recomputed on
mismatch), never a field an operator or API client can directly overwrite.
