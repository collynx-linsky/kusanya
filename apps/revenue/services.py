"""
The revenue engine. This is the ONLY place fee amounts are defined —
build spec principle 10: "no hard-coded pricing rules scattered across
the code." Every place that might charge a fee (control number creation,
payment success) calls into here; nothing computes TZS 50 itself.

See docs/PRICING_MODEL.md for the exact rules this implements.
"""

from decimal import Decimal

from django.contrib.contenttypes.models import ContentType

from apps.core.correlation import get_correlation_id
from apps.ledger.models import LedgerAccount, LedgerEntryType
from apps.ledger.services import post_compensating_entry, post_entry
from apps.revenue.models import RevenueEvent, RevenueEventType

# The entire fee schedule. See docs/PRICING_MODEL.md — changing a fee
# amount means changing it here, once, not hunting through billing/
# payment/control-number code for a hard-coded "50".
CONTROL_NUMBER_CREATION_FEE = Decimal("50.00")
PAYMENT_SUCCESS_FEE = Decimal("50.00")


def record_control_number_created(control_number, *, actor=None) -> RevenueEvent:
    """Charged exactly once, at genuine creation. See
    apps.control_numbers.services.get_or_create_for_bill/_for_account —
    this is only ever called from the branch where `created` is True."""
    ledger_entry = post_entry(
        tenant=control_number.tenant,
        entry_type=LedgerEntryType.PLATFORM_CONTROL_NUMBER_FEE,
        account=LedgerAccount.PLATFORM,
        amount=CONTROL_NUMBER_CREATION_FEE,
        currency=control_number.tenant.default_currency,
        reference=control_number.value,
        source=control_number,
    )
    return _record_event(
        tenant=control_number.tenant,
        event_type=RevenueEventType.CONTROL_NUMBER_CREATED,
        amount=CONTROL_NUMBER_CREATION_FEE,
        currency=control_number.tenant.default_currency,
        source=control_number,
        ledger_entry=ledger_entry,
    )


def record_control_number_reused(control_number, *, actor=None) -> RevenueEvent:
    """No fee — see docs/PRICING_MODEL.md. Recorded anyway (amount=0) so
    "how often is this control number reused" is a real, queryable
    metric, and no LedgerEntry is created for it (zero-value ledger lines
    have no financial meaning)."""
    return _record_event(
        tenant=control_number.tenant,
        event_type=RevenueEventType.CONTROL_NUMBER_REUSED,
        amount=Decimal("0"),
        currency=control_number.tenant.default_currency,
        source=control_number,
    )


def record_payment_successful(payment, *, actor=None) -> RevenueEvent:
    ledger_entry = post_entry(
        tenant=payment.tenant,
        entry_type=LedgerEntryType.PLATFORM_PAYMENT_FEE,
        account=LedgerAccount.PLATFORM,
        amount=PAYMENT_SUCCESS_FEE,
        currency=payment.currency,
        reference=payment.merchant_reference,
        source=payment,
    )
    return _record_event(
        tenant=payment.tenant,
        event_type=RevenueEventType.PAYMENT_SUCCESSFUL,
        amount=PAYMENT_SUCCESS_FEE,
        currency=payment.currency,
        source=payment,
        ledger_entry=ledger_entry,
    )


def record_payment_failed(payment, *, actor=None) -> RevenueEvent:
    return _record_event(
        tenant=payment.tenant,
        event_type=RevenueEventType.PAYMENT_FAILED,
        amount=Decimal("0"),
        currency=payment.currency,
        source=payment,
    )


def record_payment_duplicate(payment, *, actor=None) -> RevenueEvent:
    """Called when a duplicate provider callback is detected (see
    apps.payments.services.process_callback) — no fee, ever, no matter
    how many times the same event is delivered."""
    return _record_event(
        tenant=payment.tenant,
        event_type=RevenueEventType.PAYMENT_DUPLICATE,
        amount=Decimal("0"),
        currency=payment.currency,
        source=payment,
    )


def record_payment_reversed(payment, *, actor=None) -> RevenueEvent:
    return _compensate(payment, RevenueEventType.PAYMENT_REVERSED, LedgerEntryType.REVERSAL, actor=actor)


def record_payment_refunded(payment, *, actor=None) -> RevenueEvent:
    return _compensate(payment, RevenueEventType.PAYMENT_REFUNDED, LedgerEntryType.REFUND, actor=actor)


def _compensate(payment, event_type: str, ledger_entry_type: str, *, actor=None) -> RevenueEvent:
    """Reversal/refund accounting treatment (build spec section 4):
    configurable per tenant (`Tenant.fee_refund_policy`), and NEVER a
    deletion or edit of the original PAYMENT_SUCCESSFUL event/ledger
    entry — only ever a new, linked, compensating one. See
    docs/PRICING_MODEL.md#reversal--refund-accounting-treatment."""
    from apps.tenants.models import Tenant

    original_event = RevenueEvent.objects.filter(
        tenant=payment.tenant,
        event_type=RevenueEventType.PAYMENT_SUCCESSFUL,
        content_type=ContentType.objects.get_for_model(payment),
        object_id=str(payment.pk),
    ).first()

    should_clawback = (
        payment.tenant.fee_refund_policy == Tenant.FeeRefundPolicy.CLAWBACK
        and original_event is not None
        and original_event.amount > 0
    )

    ledger_entry = None
    amount = Decimal("0")
    if should_clawback:
        amount = -original_event.amount
        if original_event.ledger_entry is not None:
            ledger_entry = post_compensating_entry(
                original=original_event.ledger_entry,
                entry_type=ledger_entry_type,
                amount=amount,
                metadata={"reason": event_type},
            )

    return _record_event(
        tenant=payment.tenant,
        event_type=event_type,
        amount=amount,
        currency=payment.currency,
        source=payment,
        ledger_entry=ledger_entry,
        metadata={
            "policy": payment.tenant.fee_refund_policy,
            "original_fee": str(original_event.amount) if original_event else "0",
        },
    )


def _record_event(*, tenant, event_type, amount, currency, source, ledger_entry=None, metadata=None) -> RevenueEvent:
    return RevenueEvent.objects.create(
        tenant=tenant,
        event_type=event_type,
        amount=amount,
        currency=currency,
        content_type=ContentType.objects.get_for_model(source),
        object_id=str(source.pk),
        ledger_entry=ledger_entry,
        correlation_id=get_correlation_id(),
        metadata=metadata or {},
    )
