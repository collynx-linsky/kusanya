from unittest.mock import Mock, patch

import pytest

from apps.webhooks.models import WebhookDelivery, WebhookDeliveryStatus, WebhookEndpoint
from apps.webhooks.services import dispatch_event
from apps.webhooks.signing import build_signature, canonical_body, verify_signature
from apps.webhooks.tasks import _perform_delivery, deliver_webhook


@pytest.mark.django_db
class TestSigning:
    def test_correct_signature_verifies(self):
        body = canonical_body({"a": 1, "b": 2})
        signature = build_signature("secret", "12345", body)
        assert verify_signature("secret", "12345", body, signature) is True

    def test_wrong_secret_fails(self):
        body = canonical_body({"a": 1})
        signature = build_signature("secret-a", "12345", body)
        assert verify_signature("secret-b", "12345", body, signature) is False

    def test_tampered_body_fails(self):
        body = canonical_body({"a": 1})
        signature = build_signature("secret", "12345", body)
        tampered = canonical_body({"a": 2})
        assert verify_signature("secret", "12345", tampered, signature) is False

    def test_canonical_body_is_deterministic_regardless_of_key_order(self):
        assert canonical_body({"a": 1, "b": 2}) == canonical_body({"b": 2, "a": 1})


@pytest.mark.django_db
class TestDispatchEvent:
    def test_creates_a_delivery_per_active_subscribed_endpoint(self, make_tenant):
        tenant = make_tenant()
        WebhookEndpoint.objects.create(tenant=tenant, url="https://erp.example.com/hook")
        WebhookEndpoint.objects.create(tenant=tenant, url="https://inactive.example.com/hook", is_active=False)

        with patch("apps.webhooks.tasks.deliver_webhook.delay"):
            deliveries = dispatch_event(tenant=tenant, event_type="payment.successful", payload={"x": 1})

        assert len(deliveries) == 1
        assert WebhookDelivery.objects.filter(tenant=tenant).count() == 1

    def test_respects_event_subscription_filter(self, make_tenant):
        tenant = make_tenant()
        WebhookEndpoint.objects.create(
            tenant=tenant, url="https://erp.example.com/hook", subscribed_events=["bill.created"]
        )

        with patch("apps.webhooks.tasks.deliver_webhook.delay"):
            deliveries = dispatch_event(tenant=tenant, event_type="payment.successful", payload={})

        assert deliveries == []

    def test_does_not_dispatch_to_another_tenants_endpoint(self, make_tenant):
        tenant_a = make_tenant(name="A")
        tenant_b = make_tenant(name="B")
        WebhookEndpoint.objects.create(tenant=tenant_b, url="https://b.example.com/hook")

        with patch("apps.webhooks.tasks.deliver_webhook.delay"):
            deliveries = dispatch_event(tenant=tenant_a, event_type="payment.successful", payload={})

        assert deliveries == []


@pytest.mark.django_db
class TestDeliveryExecution:
    def test_successful_delivery_marks_delivered(self, make_tenant):
        tenant = make_tenant()
        endpoint = WebhookEndpoint.objects.create(tenant=tenant, url="https://erp.example.com/hook")
        delivery = WebhookDelivery.objects.create(
            tenant=tenant, endpoint=endpoint, event_type="payment.successful", payload={"amount": "500000"}
        )

        with patch("apps.webhooks.tasks.requests.post") as mock_post:
            mock_post.return_value = Mock(status_code=200, text="OK")
            success = _perform_delivery(delivery)

        assert success is True
        delivery.refresh_from_db()
        assert delivery.status == WebhookDeliveryStatus.DELIVERED
        assert delivery.attempt_count == 1

        # Verify the signature actually sent is independently verifiable.
        _, kwargs = mock_post.call_args
        signature_header = kwargs["headers"]["X-KUSANYA-Signature"].removeprefix("sha256=")
        timestamp = kwargs["headers"]["X-KUSANYA-Timestamp"]
        assert verify_signature(endpoint.secret, timestamp, kwargs["data"], signature_header)

    def test_non_2xx_response_is_not_marked_delivered(self, make_tenant):
        tenant = make_tenant()
        endpoint = WebhookEndpoint.objects.create(tenant=tenant, url="https://erp.example.com/hook")
        delivery = WebhookDelivery.objects.create(
            tenant=tenant, endpoint=endpoint, event_type="payment.successful", payload={}
        )

        with patch("apps.webhooks.tasks.requests.post") as mock_post:
            mock_post.return_value = Mock(status_code=500, text="Internal Server Error")
            success = _perform_delivery(delivery)

        assert success is False
        delivery.refresh_from_db()
        assert delivery.status != WebhookDeliveryStatus.DELIVERED

    def test_network_error_is_handled_without_raising(self, make_tenant):
        import requests

        tenant = make_tenant()
        endpoint = WebhookEndpoint.objects.create(tenant=tenant, url="https://unreachable.example.com/hook")
        delivery = WebhookDelivery.objects.create(
            tenant=tenant, endpoint=endpoint, event_type="payment.successful", payload={}
        )

        with patch("apps.webhooks.tasks.requests.post", side_effect=requests.ConnectionError("refused")):
            success = _perform_delivery(delivery)

        assert success is False
        delivery.refresh_from_db()
        assert delivery.attempt_count == 1

    def test_exhausting_max_attempts_moves_to_dead_letter(self, make_tenant):
        import requests

        tenant = make_tenant()
        endpoint = WebhookEndpoint.objects.create(tenant=tenant, url="https://unreachable.example.com/hook")
        delivery = WebhookDelivery.objects.create(
            tenant=tenant, endpoint=endpoint, event_type="payment.successful", payload={},
            attempt_count=5, max_attempts=6,
        )

        with patch("apps.webhooks.tasks.requests.post", side_effect=requests.ConnectionError("refused")):
            deliver_webhook.run(str(delivery.id))

        delivery.refresh_from_db()
        assert delivery.status == WebhookDeliveryStatus.DEAD_LETTER
        assert delivery.attempt_count == 6
