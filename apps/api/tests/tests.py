"""
External API tests. These are the direct proof that Phase 6 exposes the
same guarantees the portal has always had — idempotency, tenant
isolation, and correctness — over HTTP with credential-based auth,
never bypassing the service layer.
"""

import json
from decimal import Decimal

import pytest

from apps.api.credential_services import create_credential, revoke_credential, rotate_credential
from apps.api.models import ApiCredential
from apps.billing.models import Bill
from apps.customers.models import Customer


def _post(client, url, data, headers):
    return client.post(url, data=json.dumps(data), content_type="application/json", **headers)


@pytest.mark.django_db
class TestCredentialLifecycle:
    def test_creation_returns_raw_secret_but_stores_only_a_hash(self, make_tenant):
        tenant = make_tenant()
        credential, raw_secret = create_credential(tenant=tenant, name="Test")

        assert raw_secret
        assert credential.secret_hash != raw_secret
        assert credential.check_secret(raw_secret) is True
        assert credential.check_secret("wrong-secret") is False

    def test_rotation_invalidates_the_old_secret(self, make_tenant):
        tenant = make_tenant()
        credential, old_secret = create_credential(tenant=tenant, name="Test")

        new_secret = rotate_credential(credential)

        credential.refresh_from_db()
        assert credential.check_secret(old_secret) is False
        assert credential.check_secret(new_secret) is True

    def test_revoked_credential_is_flagged_inactive(self, make_tenant):
        tenant = make_tenant()
        credential, _ = create_credential(tenant=tenant, name="Test")

        revoke_credential(credential)

        credential.refresh_from_db()
        assert credential.is_active is False
        assert credential.revoked_at is not None


@pytest.mark.django_db
class TestAuthentication:
    def test_valid_credential_is_accepted(self, client, api_auth_header, make_tenant):
        tenant = make_tenant()
        headers, _credential = api_auth_header(tenant)
        response = client.get("/api/v1/institutions/me/", **headers)
        assert response.status_code == 200
        assert response.json()["name"] == tenant.name

    def test_missing_credential_is_rejected(self, client):
        response = client.get("/api/v1/institutions/me/")
        assert response.status_code in (401, 403)

    def test_wrong_secret_is_rejected(self, client, make_tenant, make_api_credential):
        tenant = make_tenant()
        credential, _real_secret = make_api_credential(tenant)
        response = client.get(
            "/api/v1/institutions/me/", HTTP_AUTHORIZATION=f"Bearer {credential.key_id}.wrong-secret"
        )
        assert response.status_code == 401

    def test_revoked_credential_is_rejected(self, client, make_tenant, make_api_credential):
        tenant = make_tenant()
        credential, raw_secret = make_api_credential(tenant)
        revoke_credential(credential)

        response = client.get(
            "/api/v1/institutions/me/", HTTP_AUTHORIZATION=f"Bearer {credential.key_id}.{raw_secret}"
        )
        assert response.status_code == 401

    def test_credential_from_inactive_tenant_is_rejected(self, client, make_tenant, make_api_credential):
        from apps.tenants.models import Tenant

        tenant = make_tenant(status=Tenant.Status.PENDING)
        credential, raw_secret = make_api_credential(tenant)

        response = client.get(
            "/api/v1/institutions/me/", HTTP_AUTHORIZATION=f"Bearer {credential.key_id}.{raw_secret}"
        )
        assert response.status_code == 401


@pytest.mark.django_db
class TestTenantIsolationViaApi:
    def test_a_credential_never_sees_another_tenants_customers(self, client, api_auth_header, make_tenant, make_customer):
        tenant_a = make_tenant(name="Tenant A")
        tenant_b = make_tenant(name="Tenant B")
        make_customer(tenant_a, full_name="Secret Customer A")

        headers_b, _ = api_auth_header(tenant_b)
        response = client.get("/api/v1/customers/", **headers_b)

        assert response.status_code == 200
        assert response.json() == []

    def test_a_credential_cannot_fetch_another_tenants_bill_by_guessing_its_id(
        self, client, api_auth_header, make_tenant, make_bill_with_control_number
    ):
        tenant_a = make_tenant(name="A")
        tenant_b = make_tenant(name="B")
        bill, _cn = make_bill_with_control_number(tenant_a)

        headers_b, _ = api_auth_header(tenant_b)
        response = client.get(f"/api/v1/bills/{bill.id}/", **headers_b)
        assert response.status_code == 404


@pytest.mark.django_db
class TestCustomerAndBillCreationIdempotency:
    def test_creating_a_customer_twice_with_same_external_reference_returns_the_same_row(
        self, client, api_auth_header, make_tenant
    ):
        tenant = make_tenant()
        headers, _ = api_auth_header(tenant)
        payload = {"full_name": "Amina Juma", "external_reference": "ERP-1"}

        first = _post(client, "/api/v1/customers/", payload, headers)
        second = _post(client, "/api/v1/customers/", payload, headers)

        assert first.status_code == 201
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        assert Customer.objects.filter(tenant=tenant, external_reference="ERP-1").count() == 1

    def test_creating_a_bill_twice_with_same_external_reference_returns_the_same_bill(
        self, client, api_auth_header, make_tenant, make_customer, make_customer_account
    ):
        tenant = make_tenant()
        headers, _ = api_auth_header(tenant)
        customer = make_customer(tenant)
        account = make_customer_account(tenant, customer)

        payload = {
            "customer_account_id": str(account.id),
            "items": [{"description": "Fee", "unit_amount": "1000"}],
            "external_reference": "INV-2026-00125",
        }
        first = _post(client, "/api/v1/bills/", payload, headers)
        second = _post(client, "/api/v1/bills/", payload, headers)

        assert first.status_code == 201
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        assert Bill.objects.filter(tenant=tenant, external_reference="INV-2026-00125").count() == 1

    def test_requesting_control_number_twice_returns_the_same_value(
        self, client, api_auth_header, make_tenant, make_bill_with_control_number
    ):
        tenant = make_tenant()
        headers, _ = api_auth_header(tenant)
        bill, existing_cn = make_bill_with_control_number(tenant)

        first = client.post(f"/api/v1/bills/{bill.id}/control-number/", **headers)
        second = client.post(f"/api/v1/bills/{bill.id}/control-number/", **headers)

        assert first.status_code == 200  # already existed (created by the fixture)
        assert second.status_code == 200
        assert first.json()["value"] == second.json()["value"] == existing_cn.value


@pytest.mark.django_db
class TestPaymentInitiationIdempotencyKey:
    def test_repeat_request_with_same_idempotency_key_header_returns_the_same_payment(
        self, client, api_auth_header, make_tenant, make_bill_with_control_number
    ):
        tenant = make_tenant()
        headers, _ = api_auth_header(tenant)
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("1000"))
        headers_with_idem = {**headers, "HTTP_IDEMPOTENCY_KEY": "ERP-PAY-1"}

        payload = {"control_number": control_number.value, "amount": "1000"}
        first = _post(client, "/api/v1/payments/", payload, headers_with_idem)
        second = _post(client, "/api/v1/payments/", payload, headers_with_idem)

        assert first.status_code == 201
        assert second.status_code == 201  # idempotent return still reports success
        assert first.json()["id"] == second.json()["id"]

        from apps.payments.models import Payment

        assert Payment.objects.filter(tenant=tenant, control_number=control_number).count() == 1


@pytest.mark.django_db
class TestFullApiFlow:
    def test_customer_to_paid_bill_entirely_via_the_api(self, client, api_auth_header, make_tenant):
        tenant = make_tenant()
        headers, _credential = api_auth_header(tenant)

        customer_resp = _post(client, "/api/v1/customers/", {"full_name": "Bahati Mkapa"}, headers)
        assert customer_resp.status_code == 201
        customer_id = customer_resp.json()["id"]

        account_resp = _post(
            client, "/api/v1/accounts/", {"customer_id": customer_id, "name": "2026 Fees"}, headers
        )
        assert account_resp.status_code == 201
        account_id = account_resp.json()["id"]

        bill_resp = _post(
            client, "/api/v1/bills/",
            {"customer_account_id": account_id, "items": [{"description": "Tuition", "unit_amount": "500000"}]},
            headers,
        )
        assert bill_resp.status_code == 201
        bill_id = bill_resp.json()["id"]
        assert bill_resp.json()["status"] == "active"

        cn_resp = client.post(f"/api/v1/bills/{bill_id}/control-number/", **headers)
        assert cn_resp.status_code == 201
        control_number_value = cn_resp.json()["value"]

        payment_resp = _post(
            client, "/api/v1/payments/", {"control_number": control_number_value, "amount": "500000"}, headers
        )
        assert payment_resp.status_code == 201
        assert payment_resp.json()["status"] == "successful"

        bill_detail = client.get(f"/api/v1/bills/{bill_id}/", **headers)
        assert bill_detail.json()["status"] == "paid"
        assert bill_detail.json()["balance"] == "0.00"


@pytest.mark.django_db
class TestOpenApiSchema:
    def test_schema_endpoint_is_served(self, client):
        response = client.get("/api/schema/")
        assert response.status_code == 200

    def test_docs_endpoint_is_served(self, client):
        response = client.get("/api/docs/")
        assert response.status_code == 200


@pytest.mark.django_db
class TestRateLimiting:
    def test_exceeding_the_configured_rate_returns_429(self, client, api_auth_header, make_tenant, monkeypatch):
        from apps.api.throttling import ApiCredentialRateThrottle

        # DRF's SimpleRateThrottle.THROTTLE_RATES is a class attribute
        # bound at import time from api_settings — overriding
        # settings.REST_FRAMEWORK at test-time doesn't reach it, so the
        # class attribute is patched directly instead.
        monkeypatch.setattr(ApiCredentialRateThrottle, "THROTTLE_RATES", {"api_credential": "2/min"})

        tenant = make_tenant()
        headers, _ = api_auth_header(tenant)

        responses = [client.get("/api/v1/institutions/me/", **headers) for _ in range(3)]

        assert responses[0].status_code == 200
        assert responses[1].status_code == 200
        assert responses[2].status_code == 429
