# Control Number Specification

**Status: not yet implemented** (Phase 2). This document specifies the
design the Control Number service must follow.

## What a control number is

A control number is the persistent reference a customer uses to pay a
bill or a customer account through a payment channel. It must be:

- Globally unique within its required scope (see "Scope" below).
- Collision-resistant and securely generated — not a predictable
  sequence.
- Persistent — the same control number is reused across multiple payments
  against the same bill/account (partial payments, recurring billing).
- Free of embedded PII: no phone numbers, names, national IDs, or other
  personal data encoded in the number itself.
- Auditable: every creation is a recorded event (see
  [../apps/audit](../apps/audit)), and every retrieval of an existing
  number is distinguishable from a creation in the audit trail and in the
  [revenue engine](PRICING_MODEL.md).

## Two modes

1. **One-time bill control numbers** — issued for a single bill, expire
   or become unusable once that bill is fully paid/expired/cancelled.
2. **Persistent account control numbers** — issued once for a
   `CustomerAccount` and reused across many bills/payment cycles (e.g. a
   recurring termly fee, a monthly rent account).

## The idempotency rule (this is the whole point)

Requesting a control number for a bill/account that already has one must
**return the existing control number**, not create a second one. This is
not optional — it's the mechanism the pricing model
([PRICING_MODEL.md](PRICING_MODEL.md)) depends on to avoid double-charging
the creation fee, and the mechanism ERPs depend on to safely retry a
"create bill" call without creating duplicate control numbers (build spec
section 14, idempotency).

Implementation requirement: the service's public entry point should be
`get_or_create_control_number(...)`, not `create_control_number(...)` —
callers should never need to check "does one exist" themselves before
calling it; the service owns that check atomically (a race between two
concurrent requests for the same new bill must not create two control
numbers — this needs a DB-level unique constraint on the
bill/account-to-control-number relationship, not just an
application-level check-then-create).

## Format

Configurable per deployment; not fixed by this document. Whatever format
is chosen must not encode sensitive personal information and must be
distinguishable by prefix/checksum from other tenants' or other
environments' (sandbox vs. production) control numbers to reduce the risk
of a mistyped number being accepted as valid elsewhere.

## Lifecycle events this service must record

Creation, retrieval-of-existing (no fee), expiry, cancellation, reversal.
Balance is never stored on the control number itself — it is always
computed from the underlying `Payment`/`PaymentAllocation` ledger records
(see [LEDGER_SPEC.md](LEDGER_SPEC.md)), never manually edited.
