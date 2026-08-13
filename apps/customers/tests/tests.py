import pytest
from django.db import IntegrityError, connection
from django.core.exceptions import FieldError

from apps.core.encrypted_fields import compute_lookup_hash
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


@pytest.mark.django_db
class TestCustomerFieldEncryption:
    """Customer.full_name/email/phone_number are encrypted at rest —
    ARCHITECTURE_DECISIONS ADR-032."""

    def test_stored_value_is_ciphertext_not_plaintext(self, make_tenant):
        tenant = make_tenant()
        customer = Customer.objects.create(
            tenant=tenant, full_name="Amina Juma", email="amina@example.com", phone_number="+255700000000"
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT full_name, email, phone_number FROM customers_customer WHERE id = %s",
                [str(customer.pk)],
            )
            raw_full_name, raw_email, raw_phone = cursor.fetchone()
        assert raw_full_name != "Amina Juma"
        assert raw_email != "amina@example.com"
        assert raw_phone != "+255700000000"
        # But the ORM transparently decrypts on read.
        customer.refresh_from_db()
        assert customer.full_name == "Amina Juma"
        assert customer.email == "amina@example.com"
        assert customer.phone_number == "+255700000000"

    def test_lookup_hash_columns_are_kept_in_sync_on_save(self, make_tenant):
        tenant = make_tenant()
        customer = Customer.objects.create(
            tenant=tenant, full_name="Amina Juma", email="Amina@Example.com", phone_number="+255700000000"
        )
        assert customer.full_name_lookup_hash == compute_lookup_hash("Amina Juma")
        # Email hash is computed against the lowercased value — search is
        # meant to be case-insensitive for email specifically.
        assert customer.email_lookup_hash == compute_lookup_hash("amina@example.com")
        assert customer.phone_number_lookup_hash == compute_lookup_hash("+255700000000")

    def test_filtering_by_the_encrypted_field_directly_is_rejected(self, make_tenant):
        with pytest.raises(FieldError):
            Customer.objects.filter(full_name="Amina Juma")

    def test_exact_match_search_finds_by_lookup_hash(self, make_tenant):
        tenant = make_tenant()
        Customer.objects.create(tenant=tenant, full_name="Amina Juma")
        found = Customer.objects.filter(full_name_lookup_hash=compute_lookup_hash("Amina Juma"))
        assert found.count() == 1
        not_found = Customer.objects.filter(full_name_lookup_hash=compute_lookup_hash("Amina"))
        assert not_found.count() == 0
