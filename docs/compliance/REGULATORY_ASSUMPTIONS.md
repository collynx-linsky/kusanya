# Regulatory Assumptions

**This document records assumptions, not legal facts.** Every statement
below marked as an assumption requires confirmation by qualified
legal/compliance counsel in each jurisdiction KUSANYA operates in before
it can be relied upon. Nothing in this codebase should be read as a
representation that KUSANYA holds any license, registration, or
regulatory approval — it holds none, as of this writing.

## What KUSANYA is (assumed posture)

Software that orchestrates billing, persistent control numbers, and
payment collection **through** licensed payment providers/partners. It
sits between an institution's own systems and those licensed providers
(see [../PRODUCT_REQUIREMENTS.md](../PRODUCT_REQUIREMENTS.md) for the
architecture diagram).

## What KUSANYA is assumed NOT to be, absent specific licensing

- A bank or deposit-taking institution.
- A payment service provider / payment system operator in its own right.
- A mobile money operator.
- A money transmitter.
- A custodian of customer or institution funds.
- An escrow provider.

**Consequence for the architecture:** KUSANYA is not designed to hold
customer or institution funds itself. Money moves from the customer,
through a licensed provider, to the institution's own account (or a
licensed settlement arrangement) — see [../MONEY_FLOW.md](../MONEY_FLOW.md)
and [../SETTLEMENT_SPEC.md](../SETTLEMENT_SPEC.md). Where the codebase
tracks "settlement," it tracks and reconciles that movement; it does not
model KUSANYA as the party holding funds in transit.

## Why the architecture keeps these separately identifiable

Build spec section 2 requires that KUSANYA's platform revenue,
institution/customer funds, provider charges, and settlement obligations
each be separately identifiable in the system — see
[../MONEY_FLOW.md](../MONEY_FLOW.md) and [../LEDGER_SPEC.md](../LEDGER_SPEC.md).
This is not just good accounting: it is what makes it possible to show a
regulator, auditor, or partner bank exactly what KUSANYA's own economic
interest is (transaction fees) versus what it merely orchestrates on
behalf of licensed parties (the underlying payment collection). A system
that nets everything into one "money in" balance cannot make that
distinction credibly.

## What is NOT claimed anywhere in this codebase

No claim of PCI-DSS, ISO 27001, SOC 2, Bank of Tanzania licensing, PDPA
(Personal Data Protection Act) certification, or TCRA authorization
exists in this codebase, its UI, or its documentation. Implementing
security controls (see [../SECURITY_ARCHITECTURE.md](../SECURITY_ARCHITECTURE.md))
is necessary groundwork for eventually pursuing such compliance — it is
not the compliance itself, and the two must never be conflated in any
customer-facing or partner-facing material.

## Provider integration posture

No real payment provider is integrated. `providers/mock/` (Phase 3) is a
clearly-labeled sandbox/mock adapter used for development and testing
only. Real provider adapters are built only once: (a) a specific licensed
provider has been contracted, and (b) their official API documentation
and real credentials are available — never speculatively, never against
invented endpoints. See
[../PAYMENT_PROVIDER_ARCHITECTURE.md](../PAYMENT_PROVIDER_ARCHITECTURE.md)
and build spec sections 43–44.

## Data protection

Tanzania's Personal Data Protection Act (2022) and its implementing
regulations plausibly apply to KUSANYA's handling of customer and
institution personal data (names, contact details, payment references).
**Assumption requiring confirmation:** the exact obligations (registration
with the Personal Data Protection Commission, data processing agreements
with tenants, cross-border transfer restrictions if infrastructure is
hosted outside Tanzania, breach notification duties) have not been
assessed by counsel as part of this Phase 1 build and must be before
production launch with real personal data.

## Before onboarding a real institution with real money

At minimum, before any tenant leaves sandbox/pending status with real
payment flows enabled: (1) confirm which entity is the actual licensed
payment provider/partner KUSANYA integrates with and the exact legal
basis for KUSANYA's role relative to them; (2) confirm PDPA obligations
per the section above; (3) confirm whether KUSANYA's transaction-fee
revenue model itself requires any registration in the relevant
jurisdiction; (4) have counsel review this document and either confirm
or correct every assumption in it. None of this has happened as of Phase
1 — this document exists so that gap is visible, not hidden.
