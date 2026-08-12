"""
These tests are the direct proof of build spec section 34's payment
scenarios: successful payment charges once, provider timeout becomes
UNKNOWN (never FAILED, never auto-retried), and a duplicate webhook
delivered three times produces exactly one financial event.
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.billing.models import BillStatus
from apps.payments.models import Payment, PaymentAllocation, PaymentCallbackEvent, PaymentStatus
from apps.payments.services import (
    initiate_payment,
    process_callback,
    query_payment,
    refund_payment,
    reverse_payment,
)
from apps.providers.base import ProviderOutcome
from apps.providers.mock import build_mock_callback_payload


@pytest.mark.django_db
class TestPaymentLifecycle:
    def test_successful_payment_updates_status_and_allocates_to_bill(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("500000"))

        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider,
            amount=Decimal("500000"),
        )

        assert payment.status == PaymentStatus.SUCCESSFUL
        assert payment.completed_at is not None
        bill.refresh_from_db()
        assert bill.status == BillStatus.PAID
        assert bill.balance == 0
        assert PaymentAllocation.objects.filter(payment=payment, bill=bill).exists()

    def test_failed_payment_does_not_affect_bill(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("500000"))

        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider,
            amount=Decimal("500000"), metadata={"mock_outcome": "failed"},
        )

        assert payment.status == PaymentStatus.FAILED
        bill.refresh_from_db()
        assert bill.status == BillStatus.ACTIVE
        assert bill.balance == Decimal("500000.00")

    def test_partial_payment_leaves_bill_partially_paid(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("500000"))

        initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("300000"),
        )

        bill.refresh_from_db()
        assert bill.status == BillStatus.PARTIALLY_PAID
        assert bill.balance == Decimal("200000.00")

    def test_multiple_payments_fully_pay_a_bill(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("1000000"))

        initiate_payment(tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("300000"))
        initiate_payment(tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("500000"))
        initiate_payment(tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("200000"))

        bill.refresh_from_db()
        assert bill.status == BillStatus.PAID
        assert bill.balance == 0
        assert Payment.objects.filter(control_number=control_number).count() == 3


@pytest.mark.django_db
class TestPaymentTimeoutHandling:
    def test_timeout_becomes_unknown_not_failed(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant)

        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider,
            amount=Decimal("500000"), metadata={"mock_outcome": "timeout"},
        )

        assert payment.status == PaymentStatus.UNKNOWN
        assert payment.status != PaymentStatus.FAILED
        bill.refresh_from_db()
        assert bill.status == BillStatus.ACTIVE  # not silently marked paid or failed

    def test_querying_an_unknown_payment_resolves_it_without_a_second_charge_attempt(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("500000"))

        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider,
            amount=Decimal("500000"), metadata={"mock_outcome": "timeout"},
        )
        assert payment.status == PaymentStatus.UNKNOWN

        query_payment(payment)

        assert payment.status == PaymentStatus.SUCCESSFUL  # the provider HAD actually succeeded
        # Only one Payment row exists — resolving UNKNOWN never creates a
        # second payment attempt.
        assert Payment.objects.filter(control_number=control_number).count() == 1
        bill.refresh_from_db()
        assert bill.status == BillStatus.PAID

    def test_querying_twice_does_not_double_allocate(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("500000"))
        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider,
            amount=Decimal("500000"), metadata={"mock_outcome": "timeout"},
        )
        query_payment(payment)
        query_payment(payment)  # calling again after already resolved must be a no-op

        assert PaymentAllocation.objects.filter(payment=payment).count() == 1


@pytest.mark.django_db
class TestPaymentInitiationIdempotency:
    def test_repeat_call_with_same_idempotency_key_returns_existing_payment(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("500000"))

        first = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider,
            amount=Decimal("500000"), idempotency_key="ERP-PAY-1",
        )
        second = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider,
            amount=Decimal("500000"), idempotency_key="ERP-PAY-1",
        )

        assert first.pk == second.pk
        assert Payment.objects.filter(control_number=control_number).count() == 1
        bill.refresh_from_db()
        # Only ONE successful payment was actually applied — not two.
        assert bill.amount_paid == Decimal("500000.00")


@pytest.mark.django_db
class TestInboundCallbackIdempotency:
    def _setup(self, make_tenant, make_bill_with_control_number, mock_provider):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("500000"))
        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider,
            amount=Decimal("500000"), metadata={"mock_outcome": "pending"},
        )
        assert payment.status == PaymentStatus.PENDING
        return tenant, bill, control_number, payment

    def test_callback_transitions_pending_payment_to_successful(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant, bill, control_number, payment = self._setup(
            make_tenant, make_bill_with_control_number, mock_provider
        )
        body, headers = build_mock_callback_payload(
            event_id="evt-100", provider_reference=payment.provider_reference, outcome=ProviderOutcome.SUCCESSFUL,
        )

        event = process_callback(provider=mock_provider, raw_payload=body, headers=headers)

        assert event.outcome == PaymentCallbackEvent.Outcome.PROCESSED
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.SUCCESSFUL
        bill.refresh_from_db()
        assert bill.status == BillStatus.PAID

    def test_same_event_delivered_three_times_produces_one_financial_event(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant, bill, control_number, payment = self._setup(
            make_tenant, make_bill_with_control_number, mock_provider
        )
        body, headers = build_mock_callback_payload(
            event_id="evt-200", provider_reference=payment.provider_reference, outcome=ProviderOutcome.SUCCESSFUL,
        )

        first = process_callback(provider=mock_provider, raw_payload=body, headers=headers)
        second = process_callback(provider=mock_provider, raw_payload=body, headers=headers)
        third = process_callback(provider=mock_provider, raw_payload=body, headers=headers)

        assert first.outcome == PaymentCallbackEvent.Outcome.PROCESSED
        assert second.outcome == PaymentCallbackEvent.Outcome.DUPLICATE
        assert third.outcome == PaymentCallbackEvent.Outcome.DUPLICATE

        # Exactly one allocation, one paid bill — not three.
        assert PaymentAllocation.objects.filter(payment=payment).count() == 1
        bill.refresh_from_db()
        assert bill.status == BillStatus.PAID
        assert bill.amount_paid == Decimal("500000.00")

    def test_callback_for_unrecognized_provider_reference_is_unmatched(self, mock_provider):
        body, headers = build_mock_callback_payload(
            event_id="evt-300", provider_reference="MOCK-DOES-NOT-EXIST", outcome=ProviderOutcome.SUCCESSFUL,
        )
        event = process_callback(provider=mock_provider, raw_payload=body, headers=headers)
        assert event.outcome == PaymentCallbackEvent.Outcome.UNMATCHED

    def test_invalid_signature_is_rejected_and_never_reaches_payment_logic(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant, bill, control_number, payment = self._setup(
            make_tenant, make_bill_with_control_number, mock_provider
        )
        body, _headers = build_mock_callback_payload(
            event_id="evt-400", provider_reference=payment.provider_reference, outcome=ProviderOutcome.SUCCESSFUL,
        )
        event = process_callback(provider=mock_provider, raw_payload=body, headers={})  # no signature

        assert event.outcome == PaymentCallbackEvent.Outcome.INVALID_SIGNATURE
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.PENDING  # unchanged


@pytest.mark.django_db
class TestRefundAndReversal:
    def test_successful_payment_can_be_refunded(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("500000"))
        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("500000"),
        )

        refund_payment(payment)

        assert payment.status == PaymentStatus.REFUNDED

    def test_successful_payment_can_be_reversed(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("500000"))
        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("500000"),
        )

        reverse_payment(payment)

        assert payment.status == PaymentStatus.REVERSED

    def test_cannot_refund_a_payment_that_never_succeeded(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("500000"))
        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider,
            amount=Decimal("500000"), metadata={"mock_outcome": "failed"},
        )

        with pytest.raises(ValidationError):
            refund_payment(payment)
