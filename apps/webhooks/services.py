"""
Entry point domain code uses to notify tenant systems of an event — never
construct a WebhookDelivery directly. See build spec section 15 for the
required event vocabulary (payment.*, bill.*, settlement.completed, ...).
"""

from django.db import transaction

from apps.core.correlation import get_correlation_id
from apps.webhooks.models import WebhookDelivery, WebhookEndpoint


def dispatch_event(*, tenant, event_type: str, payload: dict) -> list[WebhookDelivery]:
    """Creates a WebhookDelivery per active, subscribed endpoint and
    enqueues delivery — deferred until the current DB transaction commits
    (transaction.on_commit), so a Celery worker can never pick up a
    delivery task for a row it can't yet see (or, worse, for an event
    whose underlying change gets rolled back)."""
    endpoints = WebhookEndpoint.objects.filter(tenant=tenant, is_active=True)
    correlation_id = get_correlation_id()

    deliveries = []
    for endpoint in endpoints:
        if not endpoint.is_subscribed_to(event_type):
            continue
        delivery = WebhookDelivery.objects.create(
            tenant=tenant,
            endpoint=endpoint,
            event_type=event_type,
            payload=payload,
            correlation_id=correlation_id,
        )
        deliveries.append(delivery)
        _enqueue(delivery.id)

    return deliveries


def _enqueue(delivery_id) -> None:
    def _send():
        from apps.webhooks.tasks import deliver_webhook

        deliver_webhook.delay(str(delivery_id))

    transaction.on_commit(_send)
