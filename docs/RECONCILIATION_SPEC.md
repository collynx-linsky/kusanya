# Reconciliation Specification

**Status: implemented (Phase 4), scoped to what the provider interface
actually supports.** Code: `apps/reconciliation/`. Reconciliation is a
first-class module, not an afterthought — it's what turns `UNKNOWN`
payments ([PAYMENT_LIFECYCLE.md](PAYMENT_LIFECYCLE.md)) into a resolved
state safely, and what surfaces drift between KUSANYA's records and a
provider's without ever silently correcting a settled payment.

## What a reconciliation run does

`apps.reconciliation.services.run_reconciliation(tenant=...)`, in order:

1. **Resolves every `UNKNOWN` payment** for the tenant by calling
   `apps.payments.services.query_payment()` — this literally *is* "Phase
   4 is the scheduled backstop for `UNKNOWN` payments" from
   [PAYMENT_LIFECYCLE.md](PAYMENT_LIFECYCLE.md); it reuses that function
   rather than re-implementing resolution logic. If a payment is still
   `UNKNOWN` after querying, a `STUCK_UNKNOWN` exception is opened.
2. **Checks every settled (`SUCCESSFUL`/`FAILED`) payment with a
   provider reference** against the provider's own `reconcile()` view of
   it. A mismatch — the provider now disagrees with what KUSANYA has on
   record, e.g. drift from a chargeback processed provider-side — opens
   a `STATUS_MISMATCH` exception. **The payment's status is never
   silently corrected** — build spec section 4/16's "never silently
   modify a settled financial event" applies exactly here. If the
   provider has no record at all of a reference KUSANYA has, a
   `MISSING_AT_PROVIDER` exception is opened.

Verified against real PostgreSQL (Phase 4 development): 5 successful
payments reconciled cleanly (`matched=5, exceptions=0`); a deliberately
drifted provider record (`MockProviderTransaction.outcome` flipped after
the fact) was correctly flagged as `STATUS_MISMATCH` without touching the
already-`SUCCESSFUL` `Payment` row.

## What this is honestly scoped to (and can't detect)

The build spec describes comparing "internal transactions vs. provider
transactions vs. settlement records vs. institution records" and
detecting missing/duplicate/unmatched payments, wrong amounts, wrong
references, and more. What's actually built checks **KUSANYA's own
Payment records against the provider's per-reference `reconcile()`
response** — nothing more, because that's the only capability the
`PaymentProviderAdapter` interface offers (build spec section 12 lists
`reconcile()` as per-transaction, not a bulk statement/ledger pull).

This means the implementation **can** detect: a payment stuck `UNKNOWN`
that a query can resolve; a payment KUSANYA thinks is settled but the
provider disagrees about; a reference the provider has never heard of. It
**cannot** detect: a transaction that happened at the provider but that
KUSANYA never recorded at all (e.g. a customer paid a control number
through some channel KUSANYA's orchestrator never initiated or received a
callback for) — finding that requires a provider statement/settlement
file import, a genuinely different capability not built in Phase 4. This
limitation is inherent to the provider interface, not an oversight —
documented here so it's never assumed away.

## Match states — implemented as `ReconciliationException.status`

```text
OPEN → RESOLVED
```

Simpler than the build spec's full `UNMATCHED/MATCHED/PARTIALLY_MATCHED/
EXCEPTION/RESOLVED` vocabulary — a `ReconciliationRun` tracks aggregate
`matched_count`/`exception_count` (matches aren't persisted as individual
rows, only exceptions are — persisting one row per matched payment would
scale badly and adds no information a summary count doesn't already
carry), and each `ReconciliationException` is simply `OPEN` until a human
explicitly resolves it (`apps.reconciliation.services.resolve_exception`,
recording who, when, and why in `resolution_notes`) — never auto-cleared.

## Dashboards

Reconciliation exceptions are surfaced on both the platform dashboard
(count across every tenant) and the tenant dashboard (that tenant's open
exceptions, with a direct link) — build spec sections 26–27's requirement
that an institution never has to ask KUSANYA support "did this payment go
through" without a reconciliation exception already being visible if
something's unresolved.
