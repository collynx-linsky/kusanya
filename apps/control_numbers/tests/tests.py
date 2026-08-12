"""
These tests are the direct implementation-level proof of the
docs/PRICING_MODEL.md rule: a control number's creation is a one-time
event; every subsequent request for the same bill/account returns the
existing one. Phase 4's revenue engine will charge its fee based on the
`created` flag these functions return — these tests establish that flag
is trustworthy before any fee logic exists to consume it.
"""

from decimal import Decimal

import pytest

from apps.billing.services import get_or_create_bill
from apps.control_numbers.models import ControlNumber, ControlNumberStatus
from apps.control_numbers.services import get_or_create_for_account, get_or_create_for_bill


@pytest.mark.django_db
class TestControlNumberForBill:
    def _make_bill(self, tenant, account):
        bill, _ = get_or_create_bill(
            tenant=tenant,
            customer_account=account,
            items=[{"description": "Fee", "unit_amount": Decimal("500000")}],
        )
        return bill

    def test_first_request_creates_a_new_control_number(
        self, make_tenant, make_customer, make_customer_account
    ):
        tenant = make_tenant()
        account = make_customer_account(tenant, make_customer(tenant))
        bill = self._make_bill(tenant, account)

        control_number, created = get_or_create_for_bill(tenant=tenant, bill=bill)

        assert created is True
        assert control_number.value
        assert control_number.bill_id == bill.id

    def test_build_spec_example_one_creation_three_requests(
        self, make_tenant, make_customer, make_customer_account
    ):
        """Build spec section 3's worked example: create once, request the
        same one twice more, no new control number either time."""
        tenant = make_tenant()
        account = make_customer_account(tenant, make_customer(tenant))
        bill = self._make_bill(tenant, account)

        first, first_created = get_or_create_for_bill(tenant=tenant, bill=bill)
        second, second_created = get_or_create_for_bill(tenant=tenant, bill=bill)
        third, third_created = get_or_create_for_bill(tenant=tenant, bill=bill)

        assert first_created is True
        assert second_created is False
        assert third_created is False
        assert first.pk == second.pk == third.pk
        assert ControlNumber.objects.filter(bill=bill).count() == 1

    def test_a_bill_can_have_at_most_one_control_number_at_the_db_level(
        self, make_tenant, make_customer, make_customer_account
    ):
        tenant = make_tenant()
        account = make_customer_account(tenant, make_customer(tenant))
        bill = self._make_bill(tenant, account)
        get_or_create_for_bill(tenant=tenant, bill=bill)

        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            ControlNumber.objects.create(
                tenant=tenant, bill=bill, scope="one_time", value="999999999999"
            )

    def test_control_number_never_embeds_personal_data(
        self, make_tenant, make_customer, make_customer_account
    ):
        tenant = make_tenant()
        customer = make_customer(tenant, full_name="Amina Juma", phone_number="+255700000000")
        account = make_customer_account(tenant, customer)
        bill = self._make_bill(tenant, account)

        control_number, _ = get_or_create_for_bill(tenant=tenant, bill=bill)

        assert "Amina" not in control_number.value
        assert "700000000" not in control_number.value


@pytest.mark.django_db
class TestControlNumberForAccount:
    def test_first_request_creates_a_persistent_control_number(
        self, make_tenant, make_customer, make_customer_account
    ):
        tenant = make_tenant()
        account = make_customer_account(tenant, make_customer(tenant))

        control_number, created = get_or_create_for_account(tenant=tenant, customer_account=account)

        assert created is True
        assert control_number.customer_account_id == account.id
        assert control_number.status == ControlNumberStatus.ACTIVE

    def test_repeat_requests_return_the_same_active_control_number(
        self, make_tenant, make_customer, make_customer_account
    ):
        tenant = make_tenant()
        account = make_customer_account(tenant, make_customer(tenant))

        first, first_created = get_or_create_for_account(tenant=tenant, customer_account=account)
        second, second_created = get_or_create_for_account(tenant=tenant, customer_account=account)

        assert first_created is True
        assert second_created is False
        assert first.pk == second.pk

    def test_a_new_one_can_be_issued_after_the_active_one_is_cancelled(
        self, make_tenant, make_customer, make_customer_account
    ):
        """Persistent control numbers, unlike bill-bound ones, can be
        reissued — e.g. after expiry — without violating uniqueness,
        because the DB constraint only forbids two ACTIVE ones at once."""
        tenant = make_tenant()
        account = make_customer_account(tenant, make_customer(tenant))

        first, _ = get_or_create_for_account(tenant=tenant, customer_account=account)
        first.status = ControlNumberStatus.CANCELLED
        first.save(update_fields=["status"])

        second, second_created = get_or_create_for_account(tenant=tenant, customer_account=account)

        assert second_created is True
        assert second.pk != first.pk
        assert ControlNumber.objects.filter(customer_account=account).count() == 2
