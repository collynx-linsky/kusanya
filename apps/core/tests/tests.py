import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_check_reports_ok(client):
    response = client.get(reverse("core:health-check"))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["cache"] == "ok"


@pytest.mark.django_db
def test_correlation_id_is_echoed_on_response(client):
    response = client.get(reverse("core:health-check"), HTTP_X_CORRELATION_ID="abc-123")
    assert response["X-Correlation-ID"] == "abc-123"


@pytest.mark.django_db
def test_correlation_id_is_generated_when_absent(client):
    response = client.get(reverse("core:health-check"))
    assert response["X-Correlation-ID"]  # non-empty, server-generated
