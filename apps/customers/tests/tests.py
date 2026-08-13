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


@pytest.mark.django_db
class TestCustomerListSearchAndPagination:
    """apps.customers.views.customer_list — the P0 reference
    implementation of the design system's table/search/pagination
    pattern (docs/DESIGN_SYSTEM.md). Search on encrypted fields is
    exact-match only, same constraint as the admin (ADR-032)."""

    def _login(self, client, make_user, make_tenant, make_membership, tenant):
        user = make_user(email="portal@example.com")
        make_membership(user, tenant)
        client.force_login(user)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()
        return user

    def test_exact_name_search_finds_the_customer(self, client, make_user, make_tenant, make_membership):
        tenant = make_tenant()
        self._login(client, make_user, make_tenant, make_membership, tenant)
        Customer.objects.create(tenant=tenant, full_name="Amina Juma")
        Customer.objects.create(tenant=tenant, full_name="Bahati Msigwa")

        response = client.get("/customers/", {"q": "Amina Juma"})

        assert response.status_code == 200
        assert b"Amina Juma" in response.content
        assert b"Bahati Msigwa" not in response.content

    def test_partial_name_search_finds_nothing(self, client, make_user, make_tenant, make_membership):
        tenant = make_tenant()
        self._login(client, make_user, make_tenant, make_membership, tenant)
        Customer.objects.create(tenant=tenant, full_name="Amina Juma")

        response = client.get("/customers/", {"q": "Amina"})

        assert response.status_code == 200
        assert b"Amina Juma" not in response.content
        assert b"No exact match" in response.content

    def test_search_by_external_reference_still_supports_substring_match(
        self, client, make_user, make_tenant, make_membership
    ):
        """external_reference is NOT encrypted, so unlike name/email/phone
        it keeps real substring search."""
        tenant = make_tenant()
        self._login(client, make_user, make_tenant, make_membership, tenant)
        Customer.objects.create(tenant=tenant, full_name="Amina Juma", external_reference="ERP-CUST-00042")

        response = client.get("/customers/", {"q": "CUST-000"})

        assert response.status_code == 200
        assert b"Amina Juma" in response.content

    def test_htmx_request_targeting_the_table_returns_only_the_partial(
        self, client, make_user, make_tenant, make_membership
    ):
        tenant = make_tenant()
        self._login(client, make_user, make_tenant, make_membership, tenant)
        Customer.objects.create(tenant=tenant, full_name="Amina Juma")

        response = client.get(
            "/customers/", {"q": "Amina Juma"}, HTTP_HX_REQUEST="true", HTTP_HX_TARGET="kz-customer-table"
        )

        assert response.status_code == 200
        assert b"kz-sidebar" not in response.content  # shell not re-sent on a partial swap
        assert b"Amina Juma" in response.content

    def test_pagination_splits_results_across_pages(self, client, make_user, make_tenant, make_membership):
        tenant = make_tenant()
        self._login(client, make_user, make_tenant, make_membership, tenant)
        for i in range(30):
            Customer.objects.create(tenant=tenant, full_name=f"Customer {i:02d}")

        page_one = client.get("/customers/")
        page_two = client.get("/customers/", {"page": 2})

        assert page_one.status_code == 200
        assert page_two.status_code == 200
        assert page_one.context["page_obj"].paginator.count == 30
        assert page_one.context["page_obj"].paginator.num_pages == 2
        assert len(page_two.context["page_obj"].object_list) == 5


@pytest.mark.django_db
class TestCustomerCrud:
    """apps.customers.views.customer_edit/deactivate/activate — the
    Update half of CRUD that customers previously only had Create+Read
    for (docs/DESIGN_SYSTEM.md, P1 item 15)."""

    def _login_as_manager(self, client, make_user, make_tenant, make_membership):
        from apps.tenants.models import TenantRole

        tenant = make_tenant()
        user = make_user(email="manager@example.com")
        make_membership(user, tenant, role=TenantRole.ADMIN)
        client.force_login(user)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()
        return tenant

    def test_edit_updates_the_customer(self, client, make_user, make_tenant, make_membership):
        tenant = self._login_as_manager(client, make_user, make_tenant, make_membership)
        customer = Customer.objects.create(tenant=tenant, full_name="Old Name")

        response = client.post(
            f"/customers/{customer.pk}/edit/",
            {"full_name": "New Name", "email": "", "phone_number": "", "external_reference": ""},
        )

        assert response.status_code == 302
        customer.refresh_from_db()
        assert customer.full_name == "New Name"

    def test_deactivate_then_activate_round_trips_is_active(
        self, client, make_user, make_tenant, make_membership
    ):
        tenant = self._login_as_manager(client, make_user, make_tenant, make_membership)
        customer = Customer.objects.create(tenant=tenant, full_name="Amina Juma")
        assert customer.is_active is True

        client.post(f"/customers/{customer.pk}/deactivate/")
        customer.refresh_from_db()
        assert customer.is_active is False

        client.post(f"/customers/{customer.pk}/activate/")
        customer.refresh_from_db()
        assert customer.is_active is True

    def test_deactivating_does_not_delete_the_customer_or_its_accounts(
        self, client, make_user, make_tenant, make_membership
    ):
        tenant = self._login_as_manager(client, make_user, make_tenant, make_membership)
        customer = Customer.objects.create(tenant=tenant, full_name="Amina Juma")
        CustomerAccount.objects.create(tenant=tenant, customer=customer, name="Account 1")

        client.post(f"/customers/{customer.pk}/deactivate/")

        assert Customer.objects.filter(pk=customer.pk).exists()
        assert customer.accounts.count() == 1


@pytest.mark.django_db
class TestAccountCreateHtmxModal:
    """apps.customers.views.account_create — the reference
    HTMX-loaded-modal implementation (docs/DESIGN_SYSTEM.md)."""

    def _login(self, client, make_user, make_tenant, make_membership):
        from apps.tenants.models import TenantRole

        tenant = make_tenant()
        user = make_user(email="manager2@example.com")
        make_membership(user, tenant, role=TenantRole.ADMIN)
        client.force_login(user)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()
        return tenant, Customer.objects.create(tenant=tenant, full_name="Amina Juma")

    def test_htmx_get_returns_only_the_modal_form_fragment(
        self, client, make_user, make_tenant, make_membership
    ):
        tenant, customer = self._login(client, make_user, make_tenant, make_membership)

        response = client.get(f"/customers/{customer.pk}/accounts/new/", HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        assert b"kz-sidebar" not in response.content
        assert b"<form" in response.content

    def test_non_htmx_get_returns_the_full_page(self, client, make_user, make_tenant, make_membership):
        tenant, customer = self._login(client, make_user, make_tenant, make_membership)

        response = client.get(f"/customers/{customer.pk}/accounts/new/")

        assert response.status_code == 200
        assert b"kz-sidebar" in response.content

    def test_htmx_post_success_sets_hx_redirect_header(
        self, client, make_user, make_tenant, make_membership
    ):
        tenant, customer = self._login(client, make_user, make_tenant, make_membership)

        response = client.post(
            f"/customers/{customer.pk}/accounts/new/",
            {"name": "2026 fees", "revenue_source": "", "external_reference": ""},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 302
        assert response["HX-Redirect"] == response.url

    def test_htmx_post_validation_error_rerenders_the_fragment(
        self, client, make_user, make_tenant, make_membership
    ):
        tenant, customer = self._login(client, make_user, make_tenant, make_membership)

        response = client.post(
            f"/customers/{customer.pk}/accounts/new/",
            {"name": "", "revenue_source": "", "external_reference": ""},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assert b"kz-sidebar" not in response.content
        assert "HX-Redirect" not in response
