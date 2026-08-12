# Money Flow

**Status: implemented (Phase 4).** This document specifies how funds and
fees are kept separately identifiable in the ledger — see
[../docs/compliance/REGULATORY_ASSUMPTIONS.md](compliance/REGULATORY_ASSUMPTIONS.md)
for why this separation is a regulatory, not just an accounting,
requirement.

## Worked example — reproduced exactly by the implementation

A customer pays a TZS 1,000,000 fee bill (five installments of 200,000
in the actual Phase 4 verification run):

```text
Bill amount                        1,000,000 TZS
─────────────────────────────────────────────────
Institution entitlement            1,000,000 TZS   (owed to the tenant)
KUSANYA control-number fee                50 TZS   (charged once, at creation)
KUSANYA payment fee                      250 TZS   (5 x TZS 50, one per successful payment)
Provider fee                               0 TZS   (mock provider charges nothing — see below)
```

The customer's payment amount is not reduced by KUSANYA's fees — the
institution entitlement is the full amount the bill was for. The actual
ledger rows posted for each payment, verified against real PostgreSQL
during Phase 4 development:

```text
platform_control_number_fee  platform     50.00   (once, at control-number creation)
payment_received             customer  200,000.00  (x5 — per payment)
institution_entitlement      institution 200,000.00  (x5 — per payment, same amount)
platform_payment_fee         platform     50.00     (x5 — per payment)
```

Four separately identifiable amounts, exactly as build spec section 2
requires — never netted into one opaque "payment received: 200,000"
record. Institution entitlement and platform fee are commercial terms
between KUSANYA and the tenant (not decided by this document); what's
guaranteed is that they're always separately recorded, never commingled.

**Provider fee is 0 today** because only the mock/sandbox provider is
integrated and it charges nothing (see
[PAYMENT_PROVIDER_ARCHITECTURE.md](PAYMENT_PROVIDER_ARCHITECTURE.md)) —
`LedgerEntryType.PROVIDER_FEE` and `SettlementBatch.provider_fee_total`
both exist and are ready to carry a real provider's fee once one is
integrated; no code needs to change, only a real adapter needs to report
its fee.

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
account credited" is the licensed provider's/bank's responsibility.
**Implemented as:** `apps.settlement.SettlementBatch` (see
[SETTLEMENT_SPEC.md](SETTLEMENT_SPEC.md)) records that movement — its
`generate_settlement_batch()` only computes figures from already-settled
payments, and `mark_settlement_completed()` only records that a platform
admin has confirmed the licensed provider/bank already transferred the
funds. No function in this codebase debits or credits any real account;
KUSANYA is never modeled as a party that receives and redistributes funds
itself.
