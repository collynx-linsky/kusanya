"""Receipt generation. Called exactly once per successful payment — see
apps.payments.services._apply_outcome's SUCCESSFUL branch."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.payments.models import PaymentStatus
from apps.receipts.models import Receipt


def generate_receipt(payment) -> Receipt:
    """Idempotent: a payment already holding a receipt returns it
    unchanged rather than erroring or creating a second one — the
    OneToOneField on `payment` makes a second receipt for the same
    payment impossible at the database level regardless."""
    existing = Receipt.objects.filter(payment=payment).first()
    if existing is not None:
        return existing

    if payment.status != PaymentStatus.SUCCESSFUL:
        raise ValidationError(
            "A receipt can only be issued for a payment already confirmed SUCCESSFUL — "
            "see build spec section 20."
        )

    bill = payment.control_number.bill
    customer = payment.control_number.bill.customer_account.customer if bill else None
    if customer is None and payment.control_number.customer_account_id:
        customer = payment.control_number.customer_account.customer

    try:
        return Receipt.objects.create(
            tenant=payment.tenant,
            payment=payment,
            institution_name=payment.tenant.name,
            customer_name=customer.full_name if customer else "",
            bill_number=bill.bill_number if bill else "",
            control_number=payment.control_number.value,
            payment_reference=payment.merchant_reference,
            amount=payment.amount,
            currency=payment.currency,
            payment_channel_label=str(payment.channel) if payment.channel else str(payment.provider),
            remaining_balance_at_issue=bill.balance if bill else None,
        )
    except IntegrityError:
        # Lost a race with another process generating the same receipt —
        # idempotent recovery, same pattern as control numbers/bills.
        return Receipt.objects.get(payment=payment)
