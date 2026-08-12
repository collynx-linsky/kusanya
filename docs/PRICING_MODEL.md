# Pricing Model

**Status: not yet implemented** (Phase 4 — Revenue engine). This is the
exact rule set that implementation must satisfy, including the tests that
must pass before it can be considered done.

## Fee schedule

| Event | Fee |
|---|---|
| `CONTROL_NUMBER_CREATED` (genuinely new) | TZS 50 |
| `EXISTING_CONTROL_NUMBER_RETRIEVED` | TZS 0 |
| `CONTROL_NUMBER_REUSED` | TZS 0 |
| `PAYMENT_SUCCESSFUL` | TZS 50 |
| `PAYMENT_FAILED` | TZS 0 |
| `PAYMENT_REVERSED` | see "Reversal/refund" below |
| `PAYMENT_REFUNDED` | see "Reversal/refund" below |
| `PAYMENT_DUPLICATE` (duplicate webhook / duplicate payment) | TZS 0 |
| `CANCELLED_BILL` | no payment fee |

## The control-number-reuse rule, precisely

A control number's creation fee is charged **exactly once**, at the
moment a genuinely new control number is created for an account/bill. Any
subsequent request that resolves to the *same* control number — because
an ERP asked for "the control number for this bill" again, because a
customer reloaded a payment page, because of a retried API call — returns
the existing control number and charges nothing.

**Worked example** (build spec section 3):

```
Request 1: create control number         → new                → TZS 50
Request 2: request same control number   → existing returned  → TZS 0
Request 3: request same control number   → existing returned  → TZS 0
Payment 1 successful                     →                     → TZS 50
Payment 2 successful (same control no.)  →                     → TZS 50
```

One new control number + 2 successful payments = TZS 50 + TZS 50 + TZS 50
= **TZS 150** platform gross revenue from this example. (The build spec's
own five-payment example: TZS 50 + 5×TZS 50 = **TZS 300**.)

**Implementation requirement:** "is this control number new" must be
determined by the control-number service's own idempotency check (see
[CONTROL_NUMBER_SPEC.md](CONTROL_NUMBER_SPEC.md)), not inferred after the
fact from whether a fee was already charged — the fee event is a
*consequence* of the creation decision, not the other way around.

## Reversal / refund accounting treatment

Reversing or refunding a payment must **never** simply delete the
`PAYMENT_SUCCESSFUL` revenue event — build spec section 4 is explicit:
"Do not simply delete revenue records... Use immutable financial events
and compensating entries." The accounting treatment (does KUSANYA's TZS
50 payment fee get clawed back on refund? on reversal? partially?) is
configurable per tenant and must be decided as a product/finance question
before Phase 4 implementation, not assumed by this document. Whatever is
decided, it is implemented as a compensating `LedgerEntry`, never a
mutation or deletion of the original event.

## Currency

Fees above are denominated in TZS, the platform default (see
[MONEY_FLOW.md](MONEY_FLOW.md)). Tenants using another currency need an
explicit fee schedule for that currency — the architecture does not
assume a fixed TZS-to-other-currency conversion for fee purposes.

## Tests this implementation must pass (Phase 4)

Mirrors build spec section 34's critical scenarios: create control
number once → fee charged once; request same control number three times →
fee charged once total; five successful payments on one control number →
five payment fees; failed payment → no fee; duplicate webhook for the
same payment → no second fee; cancelled bill → no payment fee.
