import pytest
from django.db import IntegrityError

from apps.customers.models import Customer, CustomerAccount
from apps.customers.services import get_or_create_customer, get_or_create_customer_account


@pytest.mark.django_db
class TestCustomerIdempotency:
    def test_creating_with_new_external_reference_creates_a_customer(self, make_tenant):
        tenant = make_tenant()
        customer, created = get_or_create_customer(
            tenant=tenant, full_name="Amina Juma", external_reference="ERP-CUST-1"
        )
        assert created is True
        assert Customer.objects.filter(tenant=tenant).count() == 1

    def test_repeat_call_with_same_external_reference_returns_existing(self, make_tenant):
        tenant = make_tenant()
        first, first_created = get_or_create_customer(
            tenant=tenant, full_name="Amina Juma", external_reference="ERP-CUST-1"
        )
        second, second_created = get_or_create_customer(
            tenant=tenant, full_name="Amina Juma (retry)", external_reference="ERP-CUST-1"
        )
        assert first_created is True
        assert second_created is False
        assert first.pk == second.pk
        assert Customer.objects.filter(tenant=tenant).count() == 1

    def test_blank_external_reference_never_deduplicates(self, make_tenant):
        """Two walk-in customers with no ERP reference are two customers,
        not accidentally merged."""
        tenant = make_tenant()
        get_or_create_customer(tenant=tenant, full_name="Walk-in A")
        get_or_create_customer(tenant=tenant, full_name="Walk-in B")
        assert Customer.objects.filter(tenant=tenant).count() == 2

    def test_same_external_reference_allowed_across_different_tenants(self, make_tenant):
        tenant_a = make_tenant(name="A")
        tenant_b = make_tenant(name="B")
        get_or_create_customer(tenant=tenant_a, full_name="Amina", external_reference="SHARED-REF")
        get_or_create_customer(tenant=tenant_b, full_name="Bahati", external_reference="SHARED-REF")
        assert Customer.objects.filter(external_reference="SHARED-REF").count() == 2


@pytest.mark.django_db
class TestCustomerAccountIdempotency:
    def test_repeat_call_with_same_external_reference_returns_existing(
        self, make_tenant, make_customer
    ):
        tenant = make_tenant()
        customer = make_customer(tenant)
        first, first_created = get_or_create_customer_account(
            tenant=tenant, customer=customer, name="2026 fees", external_reference="ACC-1"
        )
        second, second_created = get_or_create_customer_account(
            tenant=tenant, customer=customer, name="2026 fees (dup)", external_reference="ACC-1"
        )
        assert first_created is True
        assert second_created is False
        assert first.pk == second.pk

    def test_customer_can_have_multiple_accounts(self, make_tenant, make_customer):
        tenant = make_tenant()
        customer = make_customer(tenant)
        CustomerAccount.objects.create(tenant=tenant, customer=customer, name="Account 1")
        CustomerAccount.objects.create(tenant=tenant, customer=customer, name="Account 2")
        assert customer.accounts.count() == 2
