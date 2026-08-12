# Reconciliation Specification

**Status: not yet implemented** (Phase 4). Reconciliation is a first-class
module, not an afterthought — it's what turns `UNKNOWN` payments
([PAYMENT_LIFECYCLE.md](PAYMENT_LIFECYCLE.md)) into a resolved state
safely.

## What gets compared

Internal KUSANYA transactions vs. provider transactions vs. settlement
records vs. institution records (where the institution's own system
exposes them).

## What it detects

Missing payment, duplicate payment, unmatched payment, wrong amount,
wrong reference, reversal, refund, settlement difference, provider delay,
unknown payment.

## Match states

```
UNMATCHED → (auto or manual match attempt) → MATCHED
                                            → PARTIALLY_MATCHED
                                            → EXCEPTION → RESOLVED
```

`EXCEPTION` is for anything an automated match can't confidently resolve
(amount mismatch, reference mismatch, provider record with no
corresponding internal payment). `RESOLVED` requires an explicit action —
a person or a well-defined automated rule — never a silent auto-clear.

## Relationship to `UNKNOWN` payments

When the payment orchestrator can't resolve a payment's true state via a
direct provider query (see [PAYMENT_LIFECYCLE.md](PAYMENT_LIFECYCLE.md)),
reconciliation is the scheduled backstop: periodically re-querying
providers and comparing against internal records for any payment still
sitting in `UNKNOWN`, until it resolves or is escalated as an
`EXCEPTION`.

## Dashboards

Reconciliation exceptions are surfaced on both the platform dashboard and
tenant finance dashboard (build spec sections 26–27) — an institution
should never have to ask KUSANYA support "did this payment go through," a
reconciliation exception should already be visible if something's
unresolved.
