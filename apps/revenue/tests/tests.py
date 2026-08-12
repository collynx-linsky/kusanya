"""
These tests are the direct proof of docs/PRICING_MODEL.md — including
the build spec's own worked example: one new control number + five
successful payments = TZS 50 + (5 x TZS 50) = TZS 300.
"""

from decimal import Decimal

import pytest

from apps.control_numbers.services import get_or_create_for_bill
from apps.ledger.models import LedgerEntry, LedgerEntryType
from apps.payments.services import initiate_payment
from apps.providers.base import ProviderOutcome
from apps.revenue.models import RevenueEvent, RevenueEventType
from apps.revenue.services import CONTROL_NUMBER_CREATION_FEE, PAYMENT_SUCCESS_FEE
from apps.tenants.models import Tenant


@pytest.mark.django_db
class TestFeeSchedule:
    def test_fee_amounts_match_the_pricing_model(self):
        assert CONTROL_NUMBER_CREATION_FEE == Decimal("50.00")
        assert PAYMENT_SUCCESS_FEE == Decimal("50.00")


@pytest.mark.django_db
class TestControlNumberFeeRule:
    def test_creation_charges_the_fee_exactly_once(
        self, make_tenant, make_customer, make_customer_account
    ):
        from decimal import Decimal as D

        from apps.billing.models import BillStatus
        from apps.billing.services import get_or_create_bill

        tenant = make_tenant()
        account = make_customer_account(tenant, make_customer(tenant))
        bill, _ = get_or_create_bill(
            tenant=tenant, customer_account=account,
            items=[{"description": "Fee", "unit_amount": D("500000")}],
        )
        bill.transition_to(BillStatus.ACTIVE)

        get_or_create_for_bill(tenant=tenant, bill=bill)  # creation
        get_or_create_for_bill(tenant=tenant, bill=bill)  # reuse
        get_or_create_for_bill(tenant=tenant, bill=bill)  # reuse

        created_events = RevenueEvent.objects.filter(
            tenant=tenant, event_type=RevenueEventType.CONTROL_NUMBER_CREATED
        )
        reused_events = RevenueEvent.objects.filter(
            tenant=tenant, event_type=RevenueEventType.CONTROL_NUMBER_REUSED
        )
        assert created_events.count() == 1
        assert created_events.first().amount == CONTROL_NUMBER_CREATION_FEE
        assert reused_events.count() == 2
        assert all(e.amount == 0 for e in reused_events)

    def test_creation_posts_a_ledger_entry_reuse_does_not(
        self, make_tenant, make_customer, make_customer_account
    ):
        from decimal import Decimal as D

        from apps.billing.models import BillStatus
        from apps.billing.services import get_or_create_bill

        tenant = make_tenant()
        account = make_customer_account(tenant, make_customer(tenant))
        bill, _ = get_or_create_bill(
            tenant=tenant, customer_account=account, items=[{"description": "Fee", "unit_amount": D("1000")}]
        )
        bill.transition_to(BillStatus.ACTIVE)

        get_or_create_for_bill(tenant=tenant, bill=bill)
        get_or_create_for_bill(tenant=tenant, bill=bill)

        fee_entries = LedgerEntry.objects.filter(
            tenant=tenant, entry_type=LedgerEntryType.PLATFORM_CONTROL_NUMBER_FEE
        )
        assert fee_entries.count() == 1
        assert fee_entries.first().amount == CONTROL_NUMBER_CREATION_FEE


@pytest.mark.django_db
class TestBuildSpecWorkedExample:
    def test_one_control_number_five_payments_equals_300(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        """Build spec section 3: TZS 50 + (5 x TZS 50) = TZS 300 platform
        gross revenue."""
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("100000"))
        # make_bill_with_control_number already creates the control
        # number once — that's the "one new control number" half.

        for _ in range(5):
            initiate_payment(
                tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("100"),
            )

        total_revenue = sum(
            (e.amount for e in RevenueEvent.objects.filter(tenant=tenant)), Decimal("0")
        )
        assert total_revenue == Decimal("300.00")

        creation_fee_total = sum(
            (
                e.amount
                for e in RevenueEvent.objects.filter(
                    tenant=tenant, event_type=RevenueEventType.CONTROL_NUMBER_CREATED
                )
            ),
            Decimal("0"),
        )
        payment_fee_total = sum(
            (
                e.amount
                for e in RevenueEvent.objects.filter(
                    tenant=tenant, event_type=RevenueEventType.PAYMENT_SUCCESSFUL
                )
            ),
            Decimal("0"),
        )
        assert creation_fee_total == Decimal("50.00")
        assert payment_fee_total == Decimal("250.00")


@pytest.mark.django_db
class TestPaymentFeeEvents:
    def test_failed_payment_charges_nothing(self, make_tenant, make_bill_with_control_number, mock_provider):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant)
        initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider,
            amount=Decimal("1000"), metadata={"mock_outcome": "failed"},
        )
        event = RevenueEvent.objects.get(tenant=tenant, event_type=RevenueEventType.PAYMENT_FAILED)
        assert event.amount == 0

    def test_duplicate_callback_charges_nothing_extra(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        from apps.payments.services import process_callback
        from apps.providers.mock import build_mock_callback_payload

        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant)
        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider,
            amount=Decimal("1000"), metadata={"mock_outcome": "pending"},
        )
        body, headers = build_mock_callback_payload(
            event_id="evt-fee-1", provider_reference=payment.provider_reference,
            outcome=ProviderOutcome.SUCCESSFUL,
        )
        process_callback(provider=mock_provider, raw_payload=body, headers=headers)
        process_callback(provider=mock_provider, raw_payload=body, headers=headers)
        process_callback(provider=mock_provider, raw_payload=body, headers=headers)

        successful_fee_total = sum(
            (
                e.amount
                for e in RevenueEvent.objects.filter(
                    tenant=tenant, event_type=RevenueEventType.PAYMENT_SUCCESSFUL
                )
            ),
            Decimal("0"),
        )
        assert successful_fee_total == PAYMENT_SUCCESS_FEE  # charged exactly once, not 3 times

        duplicate_events = RevenueEvent.objects.filter(
            tenant=tenant, event_type=RevenueEventType.PAYMENT_DUPLICATE
        )
        assert duplicate_events.count() == 2  # 2nd and 3rd delivery
        assert all(e.amount == 0 for e in duplicate_events)


@pytest.mark.django_db
class TestReversalRefundAccountingTreatment:
    def test_clawback_policy_creates_negative_compensating_event(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        from apps.payments.services import refund_payment

        tenant = make_tenant()
        assert tenant.fee_refund_policy == Tenant.FeeRefundPolicy.CLAWBACK
        bill, control_number = make_bill_with_control_number(tenant)
        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("1000"),
        )

        refund_payment(payment)

        refund_event = RevenueEvent.objects.get(tenant=tenant, event_type=RevenueEventType.PAYMENT_REFUNDED)
        assert refund_event.amount == -PAYMENT_SUCCESS_FEE

        # Net platform revenue for this payment is now zero — fee charged
        # then clawed back — but BOTH events still exist (no deletion).
        net = sum(
            (
                e.amount
                for e in RevenueEvent.objects.filter(
                    tenant=tenant,
                    event_type__in=[RevenueEventType.PAYMENT_SUCCESSFUL, RevenueEventType.PAYMENT_REFUNDED],
                )
            ),
            Decimal("0"),
        )
        assert net == Decimal("0")
        assert RevenueEvent.objects.filter(
            tenant=tenant, event_type=RevenueEventType.PAYMENT_SUCCESSFUL
        ).exists()  # original event was never deleted

    def test_retain_policy_keeps_the_fee_on_refund(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        from apps.payments.services import refund_payment

        tenant = make_tenant()
        tenant.fee_refund_policy = Tenant.FeeRefundPolicy.RETAIN
        tenant.save(update_fields=["fee_refund_policy"])
        bill, control_number = make_bill_with_control_number(tenant)
        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("1000"),
        )

        refund_payment(payment)

        refund_event = RevenueEvent.objects.get(tenant=tenant, event_type=RevenueEventType.PAYMENT_REFUNDED)
        assert refund_event.amount == 0  # fee retained, no clawback

        net = sum(
            (
                e.amount
                for e in RevenueEvent.objects.filter(
                    tenant=tenant,
                    event_type__in=[RevenueEventType.PAYMENT_SUCCESSFUL, RevenueEventType.PAYMENT_REFUNDED],
                )
            ),
            Decimal("0"),
        )
        assert net == PAYMENT_SUCCESS_FEE


@pytest.mark.django_db
class TestRevenueEventImmutability:
    def test_cannot_modify_a_revenue_event(self, make_tenant, make_bill_with_control_number, mock_provider):
        from apps.revenue.models import RevenueEventImmutableError

        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant)
        initiate_payment(tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("1000"))

        event = RevenueEvent.objects.filter(tenant=tenant, event_type=RevenueEventType.PAYMENT_SUCCESSFUL).first()
        event.amount = Decimal("999999")
        with pytest.raises(RevenueEventImmutableError):
            event.save()
