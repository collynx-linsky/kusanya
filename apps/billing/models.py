"""
Billing engine models — see docs/BILLING_SPEC.md for the full state
machine and rules this must follow.

No sector-specific fields anywhere here. A `Bill` for tuition, rent, a
clinic visit, or a membership renewal is the same model; what it's for
lives in `RevenueSource`/`metadata`, not in bespoke columns.
"""

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.encrypted_fields import EncryptedTextField
from apps.core.models import TenantScopedModel
from apps.core.money import money_field_kwargs


class RevenueSource(TenantScopedModel):
    """A tenant-defined billing category — "Tuition Fees", "Rent",
    "Consultation Fees", "Membership Dues". Purely organizational; the
    billing engine's behavior never branches on which RevenueSource a
    bill uses."""

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=32, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["tenant__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"], name="unique_revenue_source_name_per_tenant"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.tenant.name})"


class BillStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    PARTIALLY_PAID = "partially_paid", "Partially paid"
    PAID = "paid", "Paid"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"
    DISPUTED = "disputed", "Disputed"


# Allowed status transitions — see docs/BILLING_SPEC.md. Enforced in
# Bill.transition_to() so an invalid jump (e.g. DRAFT -> PAID, skipping
# ACTIVE) fails loudly instead of silently corrupting state.
ALLOWED_TRANSITIONS = {
    BillStatus.DRAFT: {BillStatus.ACTIVE, BillStatus.CANCELLED},
    BillStatus.ACTIVE: {
        BillStatus.PARTIALLY_PAID,
        BillStatus.PAID,
        BillStatus.EXPIRED,
        BillStatus.CANCELLED,
        BillStatus.DISPUTED,
    },
    BillStatus.PARTIALLY_PAID: {BillStatus.PAID, BillStatus.DISPUTED, BillStatus.CANCELLED},
    BillStatus.PAID: {BillStatus.DISPUTED},
    BillStatus.EXPIRED: set(),
    BillStatus.CANCELLED: set(),
    BillStatus.DISPUTED: {BillStatus.ACTIVE, BillStatus.PARTIALLY_PAID, BillStatus.PAID},
}


class Bill(TenantScopedModel):
    customer_account = models.ForeignKey(
        "customers.CustomerAccount", on_delete=models.PROTECT, related_name="bills"
    )
    revenue_source = models.ForeignKey(
        RevenueSource, null=True, blank=True, on_delete=models.PROTECT, related_name="bills"
    )

    bill_number = models.CharField(max_length=40, editable=False)
    status = models.CharField(max_length=20, choices=BillStatus.choices, default=BillStatus.DRAFT)

    currency = models.CharField(max_length=3, default="TZS")
    total_amount = models.DecimalField(**money_field_kwargs(default=0))

    due_date = models.DateField(null=True, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Idempotency key — see apps.billing.services.get_or_create_bill and
    # build spec section 14's INV-2026-00125 example.
    external_reference = models.CharField(max_length=100, blank=True)

    metadata = models.JSONField(default=dict, blank=True)
    # Encrypted at rest (ARCHITECTURE_DECISIONS ADR-032) — free text,
    # never externally serialized, no lookup_hash companion needed.
    notes = EncryptedTextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "bill_number"], name="unique_bill_number_per_tenant"),
            models.UniqueConstraint(
                fields=["tenant", "external_reference"],
                condition=models.Q(external_reference__gt=""),
                name="unique_bill_external_reference_per_tenant",
            ),
        ]

    def __str__(self):
        return f"{self.bill_number} ({self.tenant.name})"

    def save(self, *args, **kwargs):
        if not self.bill_number:
            self.bill_number = self._generate_bill_number()
        super().save(*args, **kwargs)

    def _generate_bill_number(self) -> str:
        # Human-scannable but not sequential/guessable: date prefix + a
        # random suffix, uniqueness enforced by the DB constraint above
        # (collision retried by the caller in the rare case it occurs —
        # see apps.billing.services.get_or_create_bill).
        return f"BILL-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"

    def recalculate_total(self, save: bool = True) -> None:
        total = self.items.aggregate(total=models.Sum("line_total"))["total"] or 0
        self.total_amount = total
        if save:
            self.save(update_fields=["total_amount", "updated_at"])

    def transition_to(self, new_status: str) -> None:
        allowed = ALLOWED_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValidationError(
                f"Cannot transition bill from '{self.status}' to '{new_status}'."
            )
        self.status = new_status
        if new_status == BillStatus.ACTIVE and self.issued_at is None:
            self.issued_at = timezone.now()
        if new_status == BillStatus.CANCELLED:
            self.cancelled_at = timezone.now()
        self.save(update_fields=["status", "issued_at", "cancelled_at", "updated_at"])

    @property
    def amount_paid(self):
        """Computed from PaymentAllocation rows (apps.payments, Phase 3)
        — never a stored/hand-edited field. See
        docs/LEDGER_SPEC.md#outstanding-balance-is-always-computed-never-stored-and-edited."""
        total = self.payment_allocations.aggregate(total=models.Sum("amount"))["total"]
        return total or 0

    @property
    def balance(self):
        return self.total_amount - self.amount_paid


class BillItem(TenantScopedModel):
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_amount = models.DecimalField(**money_field_kwargs())
    line_total = models.DecimalField(**money_field_kwargs(editable=False))

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.description} — {self.line_total}"

    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_amount
        super().save(*args, **kwargs)
