"""
Async webhook delivery. Never called from a web request directly — always
via apps.webhooks.services.dispatch_event, which enqueues this task after
the triggering transaction commits.

`_perform_delivery` is deliberately a plain function, not folded into the
Celery task body, so it's testable without exercising Celery's own retry
machinery (see apps/webhooks/tests/tests.py).
"""

import logging

import requests
from celery import shared_task
from django.utils import timezone

from apps.webhooks.models import WebhookDelivery, WebhookDeliveryStatus
from apps.webhooks.signing import build_signature, canonical_body

logger = logging.getLogger("kusanya")

REQUEST_TIMEOUT_SECONDS = 10


def _perform_delivery(delivery: WebhookDelivery) -> bool:
    """Attempts one HTTP delivery. Updates attempt_count, timestamps, and
    response fields regardless of outcome. Returns True on a 2xx
    response, False otherwise. Does not decide retry/dead-letter — that's
    the calling task's job, so this function has no Celery dependency."""
    body = canonical_body(delivery.payload)
    timestamp = str(int(timezone.now().timestamp()))
    signature = build_signature(delivery.endpoint.secret, timestamp, body)

    headers = {
        "Content-Type": "application/json",
        "X-KUSANYA-Event": delivery.event_type,
        "X-KUSANYA-Delivery-Id": str(delivery.id),
        "X-KUSANYA-Timestamp": timestamp,
        "X-KUSANYA-Signature": f"sha256={signature}",
    }

    delivery.attempt_count += 1
    delivery.last_attempted_at = timezone.now()

    try:
        response = requests.post(
            delivery.endpoint.url, data=body, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        delivery.response_status_code = None
        delivery.response_body = str(exc)[:2000]
        delivery.save(update_fields=["attempt_count", "last_attempted_at", "response_status_code", "response_body", "updated_at"])
        return False

    delivery.response_status_code = response.status_code
    delivery.response_body = response.text[:2000]
    success = 200 <= response.status_code < 300
    if success:
        delivery.status = WebhookDeliveryStatus.DELIVERED
    delivery.save(
        update_fields=[
            "attempt_count", "last_attempted_at", "response_status_code", "response_body", "status", "updated_at",
        ]
    )
    return success


@shared_task(bind=True, max_retries=6)
def deliver_webhook(self, delivery_id: str):
    try:
        delivery = WebhookDelivery.objects.select_related("endpoint").get(id=delivery_id)
    except WebhookDelivery.DoesNotExist:
        logger.warning("deliver_webhook: WebhookDelivery %s no longer exists", delivery_id)
        return

    if delivery.status == WebhookDeliveryStatus.DELIVERED:
        return  # already delivered (defensive — shouldn't normally happen)

    if _perform_delivery(delivery):
        return

    if delivery.attempt_count >= delivery.max_attempts:
        delivery.status = WebhookDeliveryStatus.DEAD_LETTER
        delivery.save(update_fields=["status", "updated_at"])
        logger.warning(
            "Webhook delivery %s to %s exhausted %s attempts; moved to dead-letter.",
            delivery.id, delivery.endpoint.url, delivery.attempt_count,
        )
        return

    delivery.status = WebhookDeliveryStatus.RETRYING
    delivery.save(update_fields=["status", "updated_at"])
    # Exponential backoff, capped at 5 minutes.
    countdown = min(2 ** delivery.attempt_count * 5, 300)
    raise self.retry(countdown=countdown)
