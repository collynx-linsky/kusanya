# Money Flow

**Status: not yet implemented** (Phase 4 — Ledger). This document
specifies how funds and fees must be kept separately identifiable once
the ledger exists — see [../docs/compliance/REGULATORY_ASSUMPTIONS.md](compliance/REGULATORY_ASSUMPTIONS.md)
for why this separation is a regulatory, not just an accounting,
requirement.

## Worked example

A customer pays a TZS 500,000 school fee bill in full, in one payment,
through a mobile money channel.

```
Bill amount                          500,000 TZS
─────────────────────────────────────────────────
Institution entitlement              500,000 TZS   (owed to the school)
KUSANYA control-number fee                50 TZS   (charged once, at creation)
KUSANYA payment fee                       50 TZS   (charged on this successful payment)
Provider fee                             ???? TZS   (set by the licensed provider, not KUSANYA)
```

The customer's payment amount (500,000) is not reduced by KUSANYA's fees
— the institution entitlement is what the bill was for; KUSANYA's and the
provider's fees are charged separately per each party's own commercial
agreement with the institution (or, depending on the eventual commercial
model, with the provider) — **not decided by this document**; it is a
product/legal decision to make explicit in the tenant's contract, and the
architecture must not assume a particular deduction model. What the
architecture *does* guarantee is that these four amounts are always
separately recorded as distinct `LedgerEntry` rows, never netted into a
single opaque "payment received: 500,000" record.

## Four things that must always be separately identifiable

1. **Institution entitlement** — what the tenant is owed.
2. **KUSANYA platform revenue** — control-number and payment fees (see
   [PRICING_MODEL.md](PRICING_MODEL.md)).
3. **Provider charges** — whatever the licensed payment provider charges
   for processing the transaction.
4. **Settlement obligations** — what still needs to move from
   provider/collection account to the institution's own account.

This is not merely good bookkeeping — build spec section 2 requires it so
that KUSANYA's own revenue, the institution's funds, and the provider's
charges can never be casually commingled or presented as if KUSANYA holds
or is entitled to funds it has no license to hold.

## Where money physically sits (and where KUSANYA has no claim)

KUSANYA does not assume it can hold customer or institution funds — see
[compliance/REGULATORY_ASSUMPTIONS.md](compliance/REGULATORY_ASSUMPTIONS.md).
Actual custody of funds between "customer paid" and "institution's bank
account credited" is the licensed provider's/bank's responsibility. The
`Settlement`/`SettlementBatch` domain (Phase 4, see
[SETTLEMENT_SPEC.md](SETTLEMENT_SPEC.md)) tracks that movement; it does
not model KUSANYA as a party that receives and redistributes the funds
itself unless and until a specific licensed arrangement says otherwise.
