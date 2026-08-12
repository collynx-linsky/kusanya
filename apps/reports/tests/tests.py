from decimal import Decimal

import pytest

from apps.billing.models import BillStatus
from apps.payments.services import initiate_payment
from apps.tenants.models import TenantRole


@pytest.mark.django_db
class TestBillsReport:
    def test_filters_by_status(
        self, client, make_user, make_tenant, make_membership, make_customer, make_customer_account
    ):
        from apps.billing.services import get_or_create_bill

        tenant = make_tenant()
        user = make_user()
        make_membership(user, tenant, role=TenantRole.FINANCE_MANAGER)
        account = make_customer_account(tenant, make_customer(tenant))
        draft_bill, _ = get_or_create_bill(
            tenant=tenant, customer_account=account, items=[{"description": "A", "unit_amount": Decimal("100")}]
        )
        active_bill, _ = get_or_create_bill(
            tenant=tenant, customer_account=account, items=[{"description": "B", "unit_amount": Decimal("200")}],
            external_reference="EXT-1",
        )
        active_bill.transition_to(BillStatus.ACTIVE)

        client.force_login(user)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()

        response = client.get("/reports/bills/", {"status": "active"})
        assert response.status_code == 200
        assert active_bill.bill_number.encode() in response.content
        assert draft_bill.bill_number.encode() not in response.content

    def test_csv_export(
        self, client, make_user, make_tenant, make_membership, make_customer, make_customer_account
    ):
        from apps.billing.services import get_or_create_bill

        tenant = make_tenant()
        user = make_user()
        make_membership(user, tenant, role=TenantRole.FINANCE_MANAGER)
        account = make_customer_account(tenant, make_customer(tenant))
        get_or_create_bill(
            tenant=tenant, customer_account=account, items=[{"description": "A", "unit_amount": Decimal("100")}]
        )

        client.force_login(user)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()

        response = client.get("/reports/bills/", {"format": "csv"})
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        assert b"Bill number" in response.content


@pytest.mark.django_db
class TestOutstandingBalancesReport:
    def test_only_shows_bills_with_positive_balance(
        self, client, make_user, make_tenant, make_membership, mock_provider, make_bill_with_control_number
    ):
        tenant = make_tenant()
        user = make_user()
        make_membership(user, tenant, role=TenantRole.FINANCE_MANAGER)

        unpaid_bill, unpaid_cn = make_bill_with_control_number(tenant, amount=Decimal("1000"))
        paid_bill, paid_cn = make_bill_with_control_number(tenant, amount=Decimal("500"))
        initiate_payment(tenant=tenant, control_number=paid_cn, provider=mock_provider, amount=Decimal("500"))

        client.force_login(user)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()

        response = client.get("/reports/outstanding-balances/")
        assert unpaid_bill.bill_number.encode() in response.content
        assert paid_bill.bill_number.encode() not in response.content


@pytest.mark.django_db
class TestCollectionsReport:
    def test_totals_reflect_successful_payments_only(
        self, client, make_user, make_tenant, make_membership, mock_provider, make_bill_with_control_number
    ):
        tenant = make_tenant()
        user = make_user()
        make_membership(user, tenant, role=TenantRole.FINANCE_MANAGER)

        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("1000"))
        initiate_payment(tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("1000"))

        client.force_login(user)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()

        response = client.get("/reports/collections/")
        assert response.status_code == 200
        assert b"1000" in response.content
