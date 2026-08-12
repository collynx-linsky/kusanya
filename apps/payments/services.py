"""
The Payment Orchestrator. Owns: provider routing (via
apps.providers.registry), idempotent initiation, status normalization,
callback processing, and the UNKNOWN-payment rule from
docs/PAYMENT_LIFECYCLE.md — a timeout becomes UNKNOWN, never FAILED, and
is only ever resolved by querying the provider, never by blindly
retrying.

Every function here is the single place a given payment operation
happens — views/API endpoints (Phase 6) call into this, never the
provider adapter directly.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction

from apps.audit.services import record_audit_event
from apps.billing.models import Bill, BillStatus
from apps.payments.models import Payment, PaymentAllocation, PaymentCallbackEvent, PaymentStatus
from apps.providers.base import InvalidCallbackSignatureError, ProviderError, ProviderOutcome, ProviderTimeoutError
from apps.providers.registry import get_adapter
from apps.revenue.services import (
    record_payment_duplicate,
    record_payment_failed,
    record_payment_refunded,
    record_payment_reversed,
    record_payment_successful,
)

OUTCOME_TO_STATUS = {
    ProviderOutcome.SUCCESSFUL: PaymentStatus.SUCCESSFUL,
    ProviderOutcome.FAILED: PaymentStatus.FAILED,
    ProviderOutcome.PENDING: PaymentStatus.PENDING,
}


def initiate_payment(
    *,
    tenant,
    control_number,
    provider,
    channel=None,
    amount: Decimal,
    payer_reference: str = "",
    idempotency_key: str = "",
    actor=None,
    metadata: dict | None = None,
) -> Payment:
    """Idempotent by `idempotency_key` (build spec section 14): a retried
    initiation request with the same key returns the existing Payment
    without contacting the provider again."""
    if idempotency_key:
        existing = Payment.objects.filter(tenant=tenant, idempotency_key=idempotency_key).first()
        if existing is not None:
            record_audit_event(
                action="payment.initiation_deduplicated", actor=actor, tenant=tenant, target=existing
            )
            return existing

    payment = Payment.objects.create(
        tenant=tenant,
        control_number=control_number,
        provider=provider,
        channel=channel,
        amount=amount,
        currency=tenant.default_currency,
        payer_reference=payer_reference,
        idempotency_key=idempotency_key,
    )
    record_audit_event(action="payment.initiated", actor=actor, tenant=tenant, target=payment)

    adapter = get_adapter(provider)
    try:
        result = adapter.initiate_payment(
            amount=amount,
            currency=payment.currency,
            control_number=control_number.value,
            payer_reference=payer_reference,
            merchant_reference=payment.merchant_reference,
            metadata=metadata or {},
        )
    except ProviderTimeoutError:
        # THE rule: a timeout is UNKNOWN, never FAILED, and we do not
        # retry here. Resolving it requires an explicit query_payment()
        # call — see docs/PAYMENT_LIFECYCLE.md.
        payment.transition_to(
            PaymentStatus.UNKNOWN,
            failure_reason="Provider request timed out; status must be confirmed via query_payment before any further action.",
        )
        record_audit_event(action="payment.unknown", actor=actor, tenant=tenant, target=payment)
        return payment
    except ProviderError as exc:
        payment.transition_to(PaymentStatus.FAILED, failure_reason=str(exc))
        record_audit_event(
            action="payment.failed", actor=actor, tenant=tenant, target=payment, metadata={"reason": str(exc)}
        )
        record_payment_failed(payment, actor=actor)
        _notify(payment, "payment_failed")
        return payment

    payment.provider_reference = result.provider_reference
    payment.raw_provider_response = result.raw_response
    payment.save(update_fields=["provider_reference", "raw_provider_response", "updated_at"])

    _apply_outcome(payment, result.outcome, actor=actor)
    return payment


def query_payment(payment: Payment, *, actor=None) -> Payment:
    """The only safe way to resolve an UNKNOWN payment. Never call
    initiate_payment() again to "retry" — that risks a duplicate charge
    if the original request actually succeeded at the provider."""
    adapter = get_adapter(payment.provider)
    result = adapter.query_payment(merchant_reference=payment.merchant_reference)

    if result.provider_reference and not payment.provider_reference:
        payment.provider_reference = result.provider_reference
        payment.save(update_fields=["provider_reference", "updated_at"])

    record_audit_event(
        action="payment.queried",
        actor=actor,
        tenant=payment.tenant,
        target=payment,
        metadata={"provider_outcome": result.outcome.value},
    )
    _apply_outcome(payment, result.outcome, actor=actor)
    return payment


def process_callback(*, provider, raw_payload: bytes, headers: dict, actor=None) -> PaymentCallbackEvent:
    """Inbound provider callback handling. The SAME event delivered three
    times must produce exactly one financial event — enforced by the
    UniqueConstraint on (provider, external_event_id), not merely by
    convention. See apps.payments.models.PaymentCallbackEvent."""
    adapter = get_adapter(provider)

    try:
        parsed = adapter.process_callback(raw_payload=raw_payload, headers=headers)
    except InvalidCallbackSignatureError:
        event = PaymentCallbackEvent.objects.create(
            provider=provider,
            external_event_id="",
            outcome=PaymentCallbackEvent.Outcome.INVALID_SIGNATURE,
        )
        record_audit_event(action="payment.callback_invalid_signature", actor=actor, target=event)
        return event

    try:
        with transaction.atomic():
            event = PaymentCallbackEvent.objects.create(
                provider=provider,
                external_event_id=parsed.external_event_id,
                outcome=PaymentCallbackEvent.Outcome.PROCESSED,
                raw_payload=parsed.raw_response,
            )
    except IntegrityError:
        # A second delivery of an event_id we've already processed. Log
        # it distinctly (blank external_event_id so it doesn't collide
        # with the original row) but DO NOT reprocess — no second status
        # transition, no second webhook dispatch.
        original = PaymentCallbackEvent.objects.filter(
            provider=provider, external_event_id=parsed.external_event_id
        ).first()
        dup = PaymentCallbackEvent.objects.create(
            provider=provider,
            external_event_id="",
            outcome=PaymentCallbackEvent.Outcome.DUPLICATE,
            payment=original.payment if original else None,
            raw_payload=parsed.raw_response,
        )
        record_audit_event(
            action="payment.callback_duplicate",
            actor=actor,
            tenant=original.payment.tenant if original and original.payment else None,
            target=dup,
        )
        if original is not None and original.payment is not None:
            record_payment_duplicate(original.payment, actor=actor)
        return dup

    payment = Payment.objects.filter(provider_reference=parsed.provider_reference).first()
    if payment is None:
        event.outcome = PaymentCallbackEvent.Outcome.UNMATCHED
        event.save(update_fields=["outcome"])
        record_audit_event(action="payment.callback_unmatched", actor=actor, target=event)
        return event

    event.payment = payment
    event.save(update_fields=["payment"])
    _apply_outcome(payment, parsed.outcome, actor=actor)
    return event


def refund_payment(payment: Payment, *, amount: Decimal | None = None, actor=None) -> Payment:
    if payment.status != PaymentStatus.SUCCESSFUL:
        from django.core.exceptions import ValidationError

        raise ValidationError("Only a successful payment can be refunded.")
    refund_amount = amount if amount is not None else payment.amount

    adapter = get_adapter(payment.provider)
    result = adapter.refund(provider_reference=payment.provider_reference, amount=refund_amount)
    if result.outcome == ProviderOutcome.SUCCESSFUL:
        payment.transition_to(PaymentStatus.REFUNDED)
        record_audit_event(
            action="payment.refunded", actor=actor, tenant=payment.tenant, target=payment,
            metadata={"amount": str(refund_amount)},
        )
        record_payment_refunded(payment, actor=actor)
        _dispatch(payment, "payment.refunded")
        _notify(payment, "payment_refunded")
    return payment


def reverse_payment(payment: Payment, *, actor=None) -> Payment:
    if payment.status != PaymentStatus.SUCCESSFUL:
        from django.core.exceptions import ValidationError

        raise ValidationError("Only a successful payment can be reversed.")

    adapter = get_adapter(payment.provider)
    result = adapter.reverse(provider_reference=payment.provider_reference)
    if result.outcome == ProviderOutcome.SUCCESSFUL:
        payment.transition_to(PaymentStatus.REVERSED)
        record_audit_event(action="payment.reversed", actor=actor, tenant=payment.tenant, target=payment)
        record_payment_reversed(payment, actor=actor)
        _dispatch(payment, "payment.reversed")
        _notify(payment, "payment_reversed")
    return payment


def _apply_outcome(payment: Payment, outcome: ProviderOutcome, *, actor=None) -> None:
    if outcome == ProviderOutcome.UNKNOWN:
        if payment.status in (PaymentStatus.INITIATED, PaymentStatus.PENDING):
            payment.transition_to(PaymentStatus.UNKNOWN)
            record_audit_event(action="payment.unknown", actor=actor, tenant=payment.tenant, target=payment)
        return

    target = OUTCOME_TO_STATUS[outcome]
    if payment.status == target:
        # Idempotent no-op: this outcome was already applied (e.g. a
        # query_payment() call confirming a status we already recorded).
        # Do not re-fire audit events or webhooks for it.
        return

    payment.transition_to(target)

    if target == PaymentStatus.SUCCESSFUL:
        record_audit_event(action="payment.successful", actor=actor, tenant=payment.tenant, target=payment)
        _post_settlement_ledger_entries(payment)
        record_payment_successful(payment, actor=actor)  # posts the platform's own fee entry
        _allocate_to_bill(payment)
        receipt = _generate_receipt(payment)
        _notify_payment_successful(payment, receipt)
        _dispatch(payment, "payment.successful")
    elif target == PaymentStatus.FAILED:
        record_audit_event(action="payment.failed", actor=actor, tenant=payment.tenant, target=payment)
        record_payment_failed(payment, actor=actor)
        _notify(payment, "payment_failed")
        _dispatch(payment, "payment.failed")
    elif target == PaymentStatus.PENDING:
        record_audit_event(action="payment.pending", actor=actor, tenant=payment.tenant, target=payment)
        _notify(payment, "payment_pending")
        _dispatch(payment, "payment.pending")


def _post_settlement_ledger_entries(payment: Payment) -> None:
    """The two entries build spec section 2/16 requires be separately
    identifiable for every successful payment: what the institution is
    owed (the full payment amount — KUSANYA's fee is a separate charge,
    not a deduction from it) and the gross amount received. The
    platform's own fee entry is posted separately by
    apps.revenue.services.record_payment_successful. See
    docs/MONEY_FLOW.md for the worked example this mirrors exactly."""
    from apps.ledger.models import LedgerAccount, LedgerEntryType
    from apps.ledger.services import post_entry

    post_entry(
        tenant=payment.tenant,
        entry_type=LedgerEntryType.PAYMENT_RECEIVED,
        account=LedgerAccount.CUSTOMER,
        amount=payment.amount,
        currency=payment.currency,
        reference=payment.merchant_reference,
        source=payment,
    )
    post_entry(
        tenant=payment.tenant,
        entry_type=LedgerEntryType.INSTITUTION_ENTITLEMENT,
        account=LedgerAccount.INSTITUTION,
        amount=payment.amount,
        currency=payment.currency,
        reference=payment.merchant_reference,
        source=payment,
    )


def _allocate_to_bill(payment: Payment) -> None:
    """Only handles the simple case: a one-time (bill-bound) control
    number, allocating the full payment to that one bill. Persistent
    (account-bound) control numbers spanning multiple bills need
    allocation logic (e.g. oldest-bill-first) that belongs to the ledger
    proper — not built yet, tracked in docs/PAYMENT_LIFECYCLE.md."""
    bill = payment.control_number.bill
    if bill is None:
        return

    PaymentAllocation.objects.create(
        tenant=payment.tenant, payment=payment, bill=bill, amount=payment.amount
    )

    if bill.status not in (BillStatus.ACTIVE, BillStatus.PARTIALLY_PAID):
        return
    if bill.balance <= 0:
        bill.transition_to(BillStatus.PAID)
    elif bill.status == BillStatus.ACTIVE:
        bill.transition_to(BillStatus.PARTIALLY_PAID)


def _dispatch(payment: Payment, event_type: str) -> None:
    from apps.webhooks.services import dispatch_event

    bill = payment.control_number.bill
    dispatch_event(
        tenant=payment.tenant,
        event_type=event_type,
        payload={
            "payment_id": str(payment.id),
            "merchant_reference": payment.merchant_reference,
            "provider_reference": payment.provider_reference,
            "control_number": payment.control_number.value,
            "bill_number": bill.bill_number if bill is not None else None,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "status": payment.status,
        },
    )


def _customer_for_payment(payment: Payment):
    control_number = payment.control_number
    if control_number.bill_id:
        return control_number.bill.customer_account.customer
    return control_number.customer_account.customer


def _notification_context(payment: Payment, customer, **extra) -> dict:
    bill = payment.control_number.bill
    context = {
        "institution_name": payment.tenant.name,
        "customer_name": customer.full_name,
        "bill_number": bill.bill_number if bill is not None else "",
        "control_number": payment.control_number.value,
        "payment_reference": payment.merchant_reference,
    }
    context.update(extra)
    return context


def _notify(payment: Payment, event_type: str, **extra_context) -> None:
    from apps.notifications.services import send_notification

    customer = _customer_for_payment(payment)
    send_notification(
        tenant=payment.tenant,
        event_type=event_type,
        context=_notification_context(payment, customer, **extra_context),
        recipient_email=customer.email,
        recipient_phone=customer.phone_number,
    )


def _generate_receipt(payment: Payment):
    from apps.receipts.services import generate_receipt

    return generate_receipt(payment)


def _notify_payment_successful(payment: Payment, receipt) -> None:
    """Picks the most specific event for this outcome — build spec
    section 19 lists PAYMENT_SUCCESSFUL, "partial payment," and "fully
    paid" as distinct notification events; sending all three for one
    payment would be redundant, so exactly one is chosen based on the
    bill's resulting status (or PAYMENT_SUCCESSFUL for a persistent
    control number with no single bill to be "fully paid")."""
    bill = payment.control_number.bill
    if bill is not None and bill.status == BillStatus.PAID:
        event_type = "bill_fully_paid"
    elif bill is not None and bill.status == BillStatus.PARTIALLY_PAID:
        event_type = "payment_partial"
    else:
        event_type = "payment_successful"

    _notify(
        payment,
        event_type,
        paid_amount=str(payment.amount),
        remaining_balance=str(bill.balance) if bill is not None else "",
        receipt_number=receipt.receipt_number,
    )
