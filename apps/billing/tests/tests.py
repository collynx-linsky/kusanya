from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.billing.models import Bill, BillStatus
from apps.billing.services import get_or_create_bill


@pytest.mark.django_db
class TestBillIdempotency:
    def test_creating_with_new_external_reference_creates_a_bill(
        self, make_tenant, make_customer, make_customer_account
    ):
        tenant = make_tenant()
        account = make_customer_account(tenant, make_customer(tenant))
        bill, created = get_or_create_bill(
            tenant=tenant,
            customer_account=account,
            items=[{"description": "Term 1 fees", "unit_amount": Decimal("500000")}],
            external_reference="INV-2026-00125",
        )
        assert created is True
        assert bill.total_amount == Decimal("500000.00")
        assert bill.items.count() == 1

    def test_repeat_call_with_same_external_reference_returns_existing_unchanged(
        self, make_tenant, make_customer, make_customer_account
    ):
        tenant = make_tenant()
        account = make_customer_account(tenant, make_customer(tenant))
        first, first_created = get_or_create_bill(
            tenant=tenant,
            customer_account=account,
            items=[{"description": "Term 1 fees", "unit_amount": Decimal("500000")}],
            external_reference="INV-2026-00125",
        )
        second, second_created = get_or_create_bill(
            tenant=tenant,
            customer_account=account,
            items=[{"description": "DIFFERENT ITEM", "unit_amount": Decimal("999")}],
            external_reference="INV-2026-00125",
        )
        assert first_created is True
        assert second_created is False
        assert first.pk == second.pk
        assert Bill.objects.filter(tenant=tenant).count() == 1
        # The retried call's (different) items must NOT have been applied —
        # idempotency means "you already did this," not "upsert."
        assert second.total_amount == Decimal("500000.00")

    def test_bill_number_is_generated_and_unique(
        self, make_tenant, make_customer, make_customer_account
    ):
        tenant = make_tenant()
        account = make_customer_account(tenant, make_customer(tenant))
        bill, _ = get_or_create_bill(
            tenant=tenant,
            customer_account=account,
            items=[{"description": "Fee", "unit_amount": Decimal("100")}],
        )
        assert bill.bill_number


@pytest.mark.django_db
class TestBillStateMachine:
    def _make_bill(self, tenant, account):
        bill, _ = get_or_create_bill(
            tenant=tenant,
            customer_account=account,
            items=[{"description": "Fee", "unit_amount": Decimal("100")}],
        )
        return bill

    def test_draft_bill_can_transition_to_active(
        self, make_tenant, make_customer, make_customer_account
    ):
        tenant = make_tenant()
        account = make_customer_account(tenant, make_customer(tenant))
        bill = self._make_bill(tenant, account)
        assert bill.status == BillStatus.DRAFT

        bill.transition_to(BillStatus.ACTIVE)
        assert bill.status == BillStatus.ACTIVE
        assert bill.issued_at is not None

    def test_draft_bill_cannot_jump_directly_to_paid(
        self, make_tenant, make_customer, make_customer_account
    ):
        tenant = make_tenant()
        account = make_customer_account(tenant, make_customer(tenant))
        bill = self._make_bill(tenant, account)

        with pytest.raises(ValidationError):
            bill.transition_to(BillStatus.PAID)

    def test_cancelled_bill_is_terminal(self, make_tenant, make_customer, make_customer_account):
        tenant = make_tenant()
        account = make_customer_account(tenant, make_customer(tenant))
        bill = self._make_bill(tenant, account)
        bill.transition_to(BillStatus.ACTIVE)
        bill.transition_to(BillStatus.CANCELLED)

        with pytest.raises(ValidationError):
            bill.transition_to(BillStatus.ACTIVE)

    def test_cancelling_active_bill_records_cancelled_at(
        self, make_tenant, make_customer, make_customer_account
    ):
        tenant = make_tenant()
        account = make_customer_account(tenant, make_customer(tenant))
        bill = self._make_bill(tenant, account)
        bill.transition_to(BillStatus.ACTIVE)
        bill.transition_to(BillStatus.CANCELLED)
        assert bill.cancelled_at is not None


@pytest.mark.django_db
class TestBillPortalTenantIsolation:
    def test_tenant_b_cannot_view_tenant_a_bill_by_guessing_its_url(
        self, client, make_user, make_tenant, make_membership, make_customer, make_customer_account
    ):
        tenant_a = make_tenant(name="Tenant A")
        account_a = make_customer_account(tenant_a, make_customer(tenant_a))
        bill, _ = get_or_create_bill(
            tenant=tenant_a,
            customer_account=account_a,
            items=[{"description": "Fee", "unit_amount": Decimal("100")}],
        )

        user_b = make_user(email="b@example.com")
        tenant_b = make_tenant(name="Tenant B")
        make_membership(user_b, tenant_b)
        client.force_login(user_b)
        session = client.session
        session["active_tenant_id"] = str(tenant_b.id)
        session.save()

        response = client.get(f"/bills/{bill.id}/")
        assert response.status_code == 404

    def test_tenant_b_bill_list_never_shows_tenant_a_bills(
        self, client, make_user, make_tenant, make_membership, make_customer, make_customer_account
    ):
        tenant_a = make_tenant(name="Tenant A")
        account_a = make_customer_account(tenant_a, make_customer(tenant_a))
        get_or_create_bill(
            tenant=tenant_a,
            customer_account=account_a,
            items=[{"description": "Secret Fee", "unit_amount": Decimal("100")}],
        )

        user_b = make_user(email="b2@example.com")
        tenant_b = make_tenant(name="Tenant B 2")
        make_membership(user_b, tenant_b)
        client.force_login(user_b)
        session = client.session
        session["active_tenant_id"] = str(tenant_b.id)
        session.save()

        response = client.get("/bills/")
        assert b"Secret Fee" not in response.content
