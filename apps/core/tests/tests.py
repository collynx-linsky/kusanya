import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from apps.core.ratelimit import RequestRateLimitMiddleware


def _stub_get_response(request):
    return HttpResponse("ok")


def _make_middleware(*, limit, window_seconds=60, exempt_prefixes=()):
    middleware = RequestRateLimitMiddleware(_stub_get_response)
    middleware.limit = limit
    middleware.window_seconds = window_seconds
    middleware.exempt_prefixes = exempt_prefixes
    return middleware


class TestRequestRateLimitMiddleware:
    """Exercises the middleware directly (not via override_settings) —
    it reads its config once in __init__ for per-request performance, so
    a global settings override wouldn't reach an already-constructed
    instance the way it would for a plain view function."""

    def setup_method(self):
        cache.clear()

    def test_blocks_once_the_limit_is_exceeded_within_the_window(self):
        middleware = _make_middleware(limit=3)
        factory = RequestFactory()

        def hit():
            request = factory.get("/some-view/")
            request.user = AnonymousUser()
            return middleware(request).status_code

        statuses = [hit() for _ in range(5)]
        assert statuses == [200, 200, 200, 429, 429]

    def test_exempt_prefixes_are_never_limited(self):
        middleware = _make_middleware(limit=1, exempt_prefixes=("/healthz",))
        factory = RequestFactory()

        for _ in range(5):
            request = factory.get("/healthz/")
            request.user = AnonymousUser()
            assert middleware(request).status_code == 200

    def test_a_limit_of_zero_disables_rate_limiting(self):
        middleware = _make_middleware(limit=0)
        factory = RequestFactory()

        for _ in range(10):
            request = factory.get("/some-view/")
            request.user = AnonymousUser()
            assert middleware(request).status_code == 200

    def test_fails_open_when_the_cache_backend_errors(self, monkeypatch):
        middleware = _make_middleware(limit=1)

        def _raise(*args, **kwargs):
            raise ConnectionError("cache unreachable")

        monkeypatch.setattr("apps.core.ratelimit.cache.get", _raise)
        factory = RequestFactory()
        request = factory.get("/some-view/")
        request.user = AnonymousUser()

        assert middleware(request).status_code == 200


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


@pytest.mark.django_db
class TestSystemHealthMonitorTask:
    """apps.core.tasks.monitor_system_health — the active half of
    monitoring alongside the passive /healthz/ endpoint above."""

    def test_sends_no_alert_when_everything_is_healthy(self, mailoutbox, settings):
        from apps.core.tasks import monitor_system_health

        settings.ADMINS = [("Ops", "ops@example.com")]
        result = monitor_system_health.run()

        assert result["healthy"] is True
        assert len(mailoutbox) == 0

    def test_alerts_admins_when_a_dependency_check_fails(self, mailoutbox, settings, monkeypatch):
        from apps.core import tasks as tasks_module

        settings.ADMINS = [("Ops", "ops@example.com")]
        monkeypatch.setattr(
            tasks_module,
            "run_health_checks",
            lambda: (False, {"database": "error: simulated outage"}),
        )

        result = tasks_module.monitor_system_health.run()

        assert result["healthy"] is False
        assert len(mailoutbox) == 1
        assert "health check failed" in mailoutbox[0].subject
        assert "database" in mailoutbox[0].body
        assert "ops@example.com" in mailoutbox[0].to

    def test_no_admins_configured_is_a_safe_no_op(self, mailoutbox, settings, monkeypatch):
        """mail_admins() with an empty ADMINS list is a documented Django
        no-op — confirms that behavior explicitly rather than assuming it,
        since a raised exception here would be a task failure, not just a
        missed alert."""
        from apps.core import tasks as tasks_module

        settings.ADMINS = []
        monkeypatch.setattr(
            tasks_module,
            "run_health_checks",
            lambda: (False, {"database": "error: simulated outage"}),
        )

        result = tasks_module.monitor_system_health.run()

        assert result["healthy"] is False
        assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_health_monitor_periodic_task_is_seeded_by_migration():
    from django_celery_beat.models import PeriodicTask

    task = PeriodicTask.objects.get(name="Monitor system health")
    assert task.task == "apps.core.tasks.monitor_system_health"
    assert task.enabled is True
