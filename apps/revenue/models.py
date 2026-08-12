"""
Platform revenue events. See docs/PRICING_MODEL.md for the exact fee
rules this must implement, and build spec section 4 for the required
event vocabulary.

A RevenueEvent is recorded for every event in that vocabulary — including
the zero-fee ones (`CONTROL_NUMBER_REUSED`, `PAYMENT_FAILED`,
`PAYMENT_DUPLICATE`) — because "how many control numbers were reused
this month" is itself a useful platform metric, not just "how much did we
earn." Only non-zero events get a corresponding `LedgerEntry`
(apps.ledger) — a zero-value ledger line has no financial meaning and
would just be noise in the ledger.
"""

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.core.models import TenantScopedModel
from apps.core.money import money_field_kwargs


class RevenueEventType(models.TextChoices):
    CONTROL_NUMBER_CREATED = "control_number_created", "Control number created"
    CONTROL_NUMBER_REUSED = "control_number_reused", "Control number reused"
    PAYMENT_SUCCESSFUL = "payment_successful", "Payment successful"
    PAYMENT_FAILED = "payment_failed", "Payment failed"
    PAYMENT_DUPLICATE = "payment_duplicate", "Duplicate payment/webhook"
    PAYMENT_REVERSED = "payment_reversed", "Payment reversed"
    PAYMENT_REFUNDED = "payment_refunded", "Payment refunded"


class RevenueEventImmutableError(Exception):
    pass


class RevenueEvent(TenantScopedModel):
    event_type = models.CharField(max_length=32, choices=RevenueEventType.choices, db_index=True)
    amount = models.DecimalField(**money_field_kwargs())
    currency = models.CharField(max_length=3, default="TZS")

    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.PROTECT)
    object_id = models.CharField(max_length=64, blank=True)
    source = GenericForeignKey("content_type", "object_id")

    ledger_entry = models.ForeignKey(
        "ledger.LedgerEntry", null=True, blank=True, on_delete=models.PROTECT, related_name="revenue_events"
    )
    correlation_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "event_type", "created_at"])]

    def __str__(self):
        return f"{self.get_event_type_display()}: {self.amount} {self.currency} ({self.tenant.name})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RevenueEventImmutableError("Revenue events cannot be modified after creation.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RevenueEventImmutableError(
            "Revenue events cannot be deleted. A reversal/refund is its own compensating event, "
            "never a deletion of the original — see docs/PRICING_MODEL.md."
        )
