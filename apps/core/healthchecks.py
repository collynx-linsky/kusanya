"""The actual dependency checks, shared between the HTTP probe
(apps.core.views.health_check, for an external uptime monitor / load
balancer) and the periodic Celery Beat task (apps.core.tasks.monitor_system_health,
for actual alerting when nothing external is polling the HTTP endpoint).
One implementation, two callers — see ARCHITECTURE_DECISIONS ADR-031."""


def run_health_checks() -> tuple[bool, dict]:
    """Returns (healthy, checks) — never raises. Every check is wrapped
    individually so one dependency being down doesn't prevent reporting
    on the others."""
    checks = {}
    healthy = True

    try:
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 — health check must not raise
        checks["database"] = f"error: {exc}"
        healthy = False

    try:
        from django.core.cache import cache

        cache.set("healthz", "1", timeout=5)
        checks["cache"] = "ok" if cache.get("healthz") == "1" else "error: read-back mismatch"
        if checks["cache"] != "ok":
            healthy = False
    except Exception as exc:  # noqa: BLE001
        checks["cache"] = f"error: {exc}"
        healthy = False

    try:
        import redis as redis_lib
        from django.conf import settings

        broker_client = redis_lib.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=2)
        broker_client.ping()
        checks["celery_broker"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["celery_broker"] = f"error: {exc}"
        healthy = False

    return healthy, checks
