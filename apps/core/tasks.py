"""The active half of monitoring — /healthz/ (apps.core.views.health_check)
only helps if something external is actually polling it. This task runs
the same checks on a Celery Beat schedule and emails platform admins
(settings.ADMINS, from PLATFORM_ALERT_EMAILS) when something's down, so a
failure is noticed even with no uptime monitor wired up yet. See
ARCHITECTURE_DECISIONS ADR-031."""

import logging

from celery import shared_task
from django.core.mail import mail_admins

from apps.core.healthchecks import run_health_checks

logger = logging.getLogger("kusanya")


@shared_task(name="apps.core.tasks.monitor_system_health")
def monitor_system_health() -> dict:
    healthy, checks = run_health_checks()

    if not healthy:
        logger.error("Scheduled health check failed: %s", checks)
        mail_admins(
            subject="KUSANYA health check failed",
            message="One or more dependency checks failed:\n\n"
            + "\n".join(f"- {name}: {result}" for name, result in checks.items()),
            fail_silently=True,  # a broken alert channel must not fail the task or mask the real problem in Celery's own error tracking
        )
    else:
        logger.info("Scheduled health check passed: %s", checks)

    return {"healthy": healthy, "checks": checks}
