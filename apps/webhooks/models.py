"""
Outbound webhook delivery to tenant-configured endpoints (ERPs, POS,
hospital/hotel systems, ...). See build spec section 15.

Distinct from apps.payments.PaymentCallbackEvent, which is INBOUND —
provider-to-KUSANYA. This is KUSANYA-to-tenant-system.
"""

import secrets

from django.db import models

from apps.core.models import TenantScopedModel


def _generate_secret() -> str:
    return secrets.token_hex(32)


class WebhookEndpoint(TenantScopedModel):
    url = models.URLField(max_length=500)
    secret = models.CharField(max_length=64, default=_generate_secret, editable=False)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    # Empty list = subscribed to every event type. A non-empty list
    # restricts delivery to just those event types (e.g.
    # ["payment.successful", "payment.failed"]).
    subscribed_events = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["tenant__name", "url"]

    def __str__(self):
        return f"{self.url} ({self.tenant.name})"

    def is_subscribed_to(self, event_type: str) -> bool:
        return not self.subscribed_events or event_type in self.subscribed_events


class WebhookDeliveryStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RETRYING = "retrying", "Retrying"
    DELIVERED = "delivered", "Delivered"
    DEAD_LETTER = "dead_letter", "Dead letter"


class WebhookDelivery(TenantScopedModel):
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name="deliveries")
    event_type = models.CharField(max_length=50, db_index=True)
    payload = models.JSONField(default=dict)

    status = models.CharField(
        max_length=16, choices=WebhookDeliveryStatus.choices, default=WebhookDeliveryStatus.PENDING
    )
    attempt_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=6)
    last_attempted_at = models.DateTimeField(null=True, blank=True)

    response_status_code = models.PositiveIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)

    correlation_id = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self):
        return f"{self.event_type} -> {self.endpoint.url} ({self.status})"
