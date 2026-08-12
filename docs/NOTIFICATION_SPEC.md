# Notification Specification

**Status: implemented (Phase 5).** Code: `apps/notifications/`,
`apps/receipts/`. This document specifies the design and records what's
actually live, verified end to end against real infrastructure (Redis,
Celery, the locmem/console email backend) during Phase 5 development.

## Channels

**Implemented:** email (via Django's configured `EMAIL_BACKEND` —
console in development, locmem in tests) and a MOCK/SANDBOX SMS channel
that logs what *would* be sent rather than calling a real gateway — no
SMS/WhatsApp provider is integrated (build spec sections 39/43: no
invented provider credentials or APIs). See
`apps/notifications/tasks.py::_deliver_mock_sms`.

**Architecture-ready, not implemented:** WhatsApp and push. Both exist as
`NotificationChannel` choices and can hold templates today; there is no
delivery handler registered for them yet
(`apps/notifications/tasks.py::_DELIVERY_HANDLERS`) — a `Notification`
created for either channel fails loudly with a clear error message
rather than silently vanishing (tested:
`test_unimplemented_channel_fails_loudly_not_silently`).

## Events — implemented and firing

Bill created, control number generated, payment pending, payment
successful *(only when neither of the two more specific events below
applies)*, partial payment, fully paid, payment failed, payment reversed,
payment refunded. **Balance reminder** exists as an event type and has a
default template, but nothing schedules it yet — it needs a periodic
Celery beat job that doesn't exist in Phase 5 (there was no existing
scheduled-job precedent in this codebase to hook it to; a natural
Phase 5+ follow-up).

**One choice worth being explicit about:** build spec section 19 lists
`PAYMENT_SUCCESSFUL`, "partial payment," and "fully paid" as three
notification events. Sending all three for a single payment would be
redundant, so `apps.payments.services._notify_payment_successful` sends
exactly **one** of them — `bill_fully_paid` if the payment completes the
bill, `payment_partial` if it doesn't, or the generic
`payment_successful` if there's no single bill to complete (a payment
against a persistent, account-level control number). Verified live: a
full-amount payment produced `bill_fully_paid`, not `payment_successful`;
a partial payment produced `payment_partial`.

## Templates — implemented as code defaults + optional tenant overrides

`apps/notifications/defaults.py` holds the default copy for every
(event, channel) pair, using exactly the variable vocabulary build spec
section 19 specifies: `{institution_name}` `{customer_name}`
`{bill_number}` `{control_number}` `{paid_amount}` `{remaining_balance}`
`{payment_reference}` `{receipt_number}`. A tenant can override any
(event, channel) pair via `apps.notifications.models.NotificationTemplate`
— `apps.notifications.services.render_template()` checks for an active
tenant override first, falling back to the default. Missing variables
render as empty string, never a `KeyError` — different events have
different available variables (a `bill_created` notification has no
`{paid_amount}`), and a template referencing an unavailable one shouldn't
crash delivery. Payment/billing/control-number code never constructs
notification text — it calls `send_notification(event_type=..., context=
{...})` with structured data only. See
[../ARCHITECTURE_DECISIONS.md](../ARCHITECTURE_DECISIONS.md) ADR-021 for
why defaults are code constants rather than database rows every tenant
starts with a copy of.

## Delivery is asynchronous — implemented

`apps.notifications.services.send_notification()` creates a `Notification`
row per channel with a usable recipient, then enqueues
`apps.notifications.tasks.deliver_notification` via
`transaction.on_commit` (same pattern as webhook delivery, ADR-015) —
never sent inline in the request/response cycle. Verified live: initiating
a payment produced `bill_created`, `control_number_generated`, and
`bill_fully_paid` notifications on both email and SMS, all reaching
`status=sent` with real timestamps once a Celery worker was running to
consume them.

## Receipts — implemented

`apps/receipts/models.py::Receipt`. Generated automatically and exactly
once per successful payment (`apps.payments.services._apply_outcome`'s
`SUCCESSFUL` branch calls `apps.receipts.services.generate_receipt`,
idempotently — a second call for the same payment returns the existing
receipt, and the `payment` field's `OneToOneField` makes a second receipt
for the same payment impossible at the database level regardless).
Fields: institution name, customer name, bill number, control number,
payment reference, amount, currency, payment channel/provider label,
receipt number, and remaining balance *at the moment the receipt was
issued*.

**Snapshotted, not live-referenced:** a receipt's fields are copied at
generation time, not foreign keys re-resolved on every view — a receipt
is a historical document; it must read the same in a year even if the
customer's name is later corrected or the bill's metadata changes. See
`apps/receipts/models.py`'s module docstring.

**Never issued speculatively:** `generate_receipt()` raises
`ValidationError` if called for a payment that isn't `SUCCESSFUL` —
there is no code path that produces a receipt for a `PENDING` or
`UNKNOWN` payment, per the build spec's explicit warning against that.
Tested directly.
