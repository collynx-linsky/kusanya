"""
Settlement. See docs/SETTLEMENT_SPEC.md and
docs/compliance/REGULATORY_ASSUMPTIONS.md — this domain records and
reconciles the movement of funds from a licensed provider to a tenant's
own account. It does NOT model KUSANYA as a party holding funds in
transit; `SettlementBatch.status` becoming COMPLETED represents a
platform admin recording that the licensed provider/bank has confirmed
the transfer, not KUSANYA performing it.
"""

import uuid

from django.db import models
from django.utils import timezone

from apps.core.encrypted_fields import EncryptedTextField
from apps.core.models import TenantScopedModel
from apps.core.money import money_field_kwargs


class SettlementStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    EXCEPTION = "exception", "Exception"


class SettlementBatch(TenantScopedModel):
    provider = models.ForeignKey("providers.PaymentProvider", on_delete=models.PROTECT, related_name="settlement_batches")
    reference = models.CharField(max_length=40, editable=False)

    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    gross_amount = models.DecimalField(**money_field_kwargs(default=0))
    platform_fee_total = models.DecimalField(**money_field_kwargs(default=0))
    provider_fee_total = models.DecimalField(**money_field_kwargs(default=0))
    net_amount = models.DecimalField(**money_field_kwargs(default=0))
    currency = models.CharField(max_length=3, default="TZS")

    status = models.CharField(max_length=16, choices=SettlementStatus.choices, default=SettlementStatus.PENDING)
    settlement_date = models.DateTimeField(null=True, blank=True)
    external_settlement_reference = models.CharField(
        max_length=150, blank=True,
        help_text="The provider/bank's own reference for the actual funds transfer — entered when marking this batch completed.",
    )
    # Encrypted at rest (ARCHITECTURE_DECISIONS ADR-032) — free text,
    # never externally serialized, no lookup_hash companion needed.
    notes = EncryptedTextField(blank=True)

    class Meta:
        ordering = ["-period_end"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "reference"], name="unique_settlement_batch_reference_per_tenant")
        ]

    def __str__(self):
        return f"{self.reference} ({self.tenant.name}, {self.status})"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"SET-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)
