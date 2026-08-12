"""
Celery application for KUSANYA.

Background workers handle everything that must not block a web request:
notifications, webhook delivery, provider polling, reconciliation,
settlement processing, report generation, retries, scheduled billing and
expiry sweeps (see docs/README.md section on background processing).

Phase 1 wires the worker and beat scheduler and proves them with a trivial
health-check task; domain tasks are added as each phase introduces them.
"""

import os

from celery import Celery
from celery.signals import setup_logging

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("kusanya")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@setup_logging.connect
def _configure_celery_logging(**kwargs):
    # Defer to Django's LOGGING config instead of Celery's default so log
    # format (including correlation IDs) stays consistent across web and
    # worker processes.
    from logging.config import dictConfig

    from django.conf import settings

    dictConfig(settings.LOGGING)


@app.task(bind=True, name="kusanya.ping")
def ping(self):
    """Trivial task used to verify worker connectivity end-to-end."""
    return "pong"
