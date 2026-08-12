from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.payments.services import initiate_payment
from apps.receipts.models import Receipt
from apps.receipts.services import generate_receipt


@pytest.mark.django_db
class TestReceiptGeneration:
    def test_receipt_is_generated_automatically_on_successful_payment(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("1000"))
        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("1000")
        )

        receipt = Receipt.objects.get(payment=payment)
        assert receipt.amount == Decimal("1000.00")
        assert receipt.institution_name == tenant.name
        assert receipt.control_number == control_number.value
        assert receipt.receipt_number

    def test_no_receipt_for_failed_payment(self, make_tenant, make_bill_with_control_number, mock_provider):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant)
        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider,
            amount=Decimal("1000"), metadata={"mock_outcome": "failed"},
        )
        assert not Receipt.objects.filter(payment=payment).exists()

    def test_generate_receipt_rejects_a_non_successful_payment(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant)
        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider,
            amount=Decimal("1000"), metadata={"mock_outcome": "failed"},
        )
        with pytest.raises(ValidationError):
            generate_receipt(payment)

    def test_calling_generate_receipt_twice_returns_the_same_receipt(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant)
        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("1000")
        )

        first = generate_receipt(payment)
        second = generate_receipt(payment)

        assert first.pk == second.pk
        assert Receipt.objects.filter(payment=payment).count() == 1

    def test_receipt_snapshots_remaining_balance_at_issue(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("1000"))
        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("400"),
        )

        receipt = Receipt.objects.get(payment=payment)
        assert receipt.remaining_balance_at_issue == Decimal("600.00")
