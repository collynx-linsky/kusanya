"""
Receipts. See build spec section 20.

A receipt is a point-in-time document — its fields are snapshotted at
generation time, not live references that could silently change if the
customer's name is edited later or a bill's metadata changes. It is only
ever generated for a payment that has already been confirmed
`SUCCESSFUL` (see apps.receipts.services.generate_receipt) — never
speculatively for `PENDING`/`UNKNOWN`, per the build spec's explicit
warning against claiming a receipt is final before that.
"""

import uuid

from django.db import models
from django.utils import timezone

from apps.core.models import TenantScopedModel
from apps.core.money import money_field_kwargs


class Receipt(TenantScopedModel):
    payment = models.OneToOneField("payments.Payment", on_delete=models.PROTECT, related_name="receipt")
    receipt_number = models.CharField(max_length=40, editable=False)
    issued_at = models.DateTimeField(default=timezone.now)

    # Snapshot — see module docstring.
    institution_name = models.CharField(max_length=200)
    customer_name = models.CharField(max_length=255)
    bill_number = models.CharField(max_length=40, blank=True)
    control_number = models.CharField(max_length=32)
    payment_reference = models.CharField(max_length=64)
    amount = models.DecimalField(**money_field_kwargs())
    currency = models.CharField(max_length=3, default="TZS")
    payment_channel_label = models.CharField(max_length=200)
    remaining_balance_at_issue = models.DecimalField(**money_field_kwargs(null=True, blank=True))

    class Meta:
        ordering = ["-issued_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "receipt_number"], name="unique_receipt_number_per_tenant")
        ]

    def __str__(self):
        return self.receipt_number

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = f"RCPT-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)
