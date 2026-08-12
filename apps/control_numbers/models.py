"""
Persistent control numbers. See docs/CONTROL_NUMBER_SPEC.md.

A control number attaches to exactly one of: a single `Bill` (one-time)
or a `CustomerAccount` (persistent, reused across many bills/payment
cycles). It never embeds personal data — see `generate_value()` in
services.py.
"""

from django.conf import settings
from django.db import models

from apps.core.models import TenantScopedModel


class ControlNumberScope(models.TextChoices):
    ONE_TIME = "one_time", "One-time (bound to a single bill)"
    PERSISTENT = "persistent", "Persistent (bound to a customer account)"


class ControlNumberStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


class ControlNumber(TenantScopedModel):
    value = models.CharField(max_length=32, unique=True, db_index=True)
    scope = models.CharField(max_length=16, choices=ControlNumberScope.choices)
    status = models.CharField(
        max_length=16, choices=ControlNumberStatus.choices, default=ControlNumberStatus.ACTIVE
    )

    # Exactly one of these is set, enforced by the CheckConstraint below.
    bill = models.OneToOneField(
        "billing.Bill", null=True, blank=True, on_delete=models.CASCADE, related_name="control_number"
    )
    customer_account = models.ForeignKey(
        "customers.CustomerAccount",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="control_numbers",
    )

    expires_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(bill__isnull=False, customer_account__isnull=True)
                    | models.Q(bill__isnull=True, customer_account__isnull=False)
                ),
                name="control_number_exactly_one_owner",
            ),
            # A persistent control number can be re-issued after
            # expiry/cancellation, but only one may be ACTIVE per account
            # at a time. One-time (bill-bound) control numbers don't need
            # an equivalent constraint — the OneToOneField on `bill`
            # already guarantees at most one control number per bill,
            # full stop.
            models.UniqueConstraint(
                fields=["customer_account"],
                condition=models.Q(status="active"),
                name="unique_active_control_number_per_account",
            ),
        ]

    def __str__(self):
        return self.value
