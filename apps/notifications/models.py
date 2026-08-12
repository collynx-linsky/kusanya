"""
Notification engine. See docs/NOTIFICATION_SPEC.md and build spec
section 19.

Two models: `NotificationTemplate` (optional per-tenant override of the
default copy in defaults.py) and `Notification` (one row per actual
message sent/attempted — the delivery record).
"""

from django.db import models

from apps.core.models import TenantScopedModel


class NotificationChannel(models.TextChoices):
    EMAIL = "email", "Email"
    SMS = "sms", "SMS"
    WHATSAPP = "whatsapp", "WhatsApp"  # architecture-ready, not implemented — see services.py
    PUSH = "push", "Push"  # architecture-ready, not implemented


class NotificationEventType(models.TextChoices):
    BILL_CREATED = "bill_created", "Bill created"
    CONTROL_NUMBER_GENERATED = "control_number_generated", "Control number generated"
    PAYMENT_PENDING = "payment_pending", "Payment pending"
    PAYMENT_SUCCESSFUL = "payment_successful", "Payment successful"
    PAYMENT_FAILED = "payment_failed", "Payment failed"
    PAYMENT_PARTIAL = "payment_partial", "Partial payment"
    BILL_FULLY_PAID = "bill_fully_paid", "Bill fully paid"
    BALANCE_REMINDER = "balance_reminder", "Balance reminder"
    PAYMENT_REVERSED = "payment_reversed", "Payment reversed"
    PAYMENT_REFUNDED = "payment_refunded", "Payment refunded"


class NotificationTemplate(TenantScopedModel):
    """A tenant's override of the default copy for one (event, channel)
    pair. Nothing needs a row here to function — see
    apps.notifications.defaults for what's used when a tenant hasn't
    customized a template."""

    event_type = models.CharField(max_length=32, choices=NotificationEventType.choices)
    channel = models.CharField(max_length=16, choices=NotificationChannel.choices)
    subject = models.CharField(max_length=255, blank=True, help_text="Ignored for SMS.")
    body = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "event_type", "channel"], name="unique_template_per_tenant_event_channel"
            )
        ]
        ordering = ["tenant__name", "event_type", "channel"]

    def __str__(self):
        return f"{self.tenant.name}: {self.get_event_type_display()} ({self.get_channel_display()})"


class NotificationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"


class Notification(TenantScopedModel):
    event_type = models.CharField(max_length=32, choices=NotificationEventType.choices, db_index=True)
    channel = models.CharField(max_length=16, choices=NotificationChannel.choices)
    recipient = models.CharField(max_length=255, help_text="Email address or phone number.")
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField()

    status = models.CharField(max_length=16, choices=NotificationStatus.choices, default=NotificationStatus.PENDING)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.CharField(max_length=500, blank=True)

    correlation_id = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]

    def __str__(self):
        return f"{self.get_event_type_display()} -> {self.recipient} ({self.status})"
