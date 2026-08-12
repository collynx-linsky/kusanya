# Notification Specification

**Status: not yet implemented** (Phase 5). This document specifies the
design of the independent notification service.

## Channels

SMS, email, WhatsApp-ready architecture, future push notifications. No
SMS/WhatsApp provider is integrated yet (build spec sections 39/43 — no
invented provider credentials or APIs); email uses Django's console
backend in development (see `config/settings/development.py`) until a
real transactional email provider is configured.

## Events (target)

Bill created, control number generated, payment pending, payment
successful, payment failed, partial payment, fully paid, balance
reminder, payment reversed, payment refunded.

## Templates, not hard-coded strings

Notification text lives in tenant-configurable templates supporting
variables: `{institution_name}`, `{customer_name}`, `{bill_number}`,
`{control_number}`, `{paid_amount}`, `{remaining_balance}`,
`{payment_reference}`, `{receipt_number}`. Payment/billing logic never
constructs notification text inline — it emits an event with structured
data; the notification service resolves that against the tenant's
template. This keeps notification copy editable per tenant without a code
change.

## Delivery is asynchronous

All sending goes through Celery background workers (already wired in
Phase 1 — see `config/celery.py`), never inline in the request/response
cycle for a payment callback or bill creation — a slow SMS gateway must
never make a payment webhook handler time out.

## Receipts

Receipt generation (build spec section 20) sits alongside notifications:
institution name, customer name, bill/reference, control number, payment
reference, amount, date/time, payment channel/provider, remaining
balance, receipt number. A receipt is not represented as final until the
payment's status is genuinely `SUCCESSFUL` per
[PAYMENT_LIFECYCLE.md](PAYMENT_LIFECYCLE.md) — never issued speculatively
for a `PENDING` or `UNKNOWN` payment.
