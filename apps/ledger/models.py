"""
The financial ledger. See docs/LEDGER_SPEC.md.

Every important financial event is a `LedgerEntry` here — bill amounts,
payment allocations, institution entitlement, platform fees, provider
fees, refunds, reversals, settlements, adjustments — each separately
identifiable (build spec section 2/16), never netted into one opaque
"payment received" row. Immutable once written: corrections are new
compensating entries, never an UPDATE or DELETE of a settled row — the
same principle already enforced for `apps.audit.AuditLog` (see
../ARCHITECTURE_DECISIONS.md ADR-006), applied here without the hash
chain (the audit log already provides platform-wide tamper-evidence;
duplicating that chain per-app would be redundant, not extra safety).
"""

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.core.models import TenantScopedModel
from apps.core.money import money_field_kwargs


class LedgerEntryType(models.TextChoices):
    BILL_AMOUNT = "bill_amount", "Bill amount"
    PAYMENT_RECEIVED = "payment_received", "Payment received"
    INSTITUTION_ENTITLEMENT = "institution_entitlement", "Institution entitlement"
    PLATFORM_CONTROL_NUMBER_FEE = "platform_control_number_fee", "Platform control-number fee"
    PLATFORM_PAYMENT_FEE = "platform_payment_fee", "Platform payment fee"
    PROVIDER_FEE = "provider_fee", "Provider fee"
    REFUND = "refund", "Refund"
    REVERSAL = "reversal", "Reversal"
    SETTLEMENT = "settlement", "Settlement"
    ADJUSTMENT = "adjustment", "Adjustment"


class LedgerAccount(models.TextChoices):
    """Whose economic position this entry affects — the
    "destination/account classification" build spec section 16 requires,
    kept separate from `entry_type` (what kind of event) on purpose: a
    REFUND can affect the CUSTOMER account or the INSTITUTION account
    depending on who is being made whole."""

    CUSTOMER = "customer", "Customer"
    INSTITUTION = "institution", "Institution (tenant)"
    PLATFORM = "platform", "KUSANYA platform"
    PROVIDER = "provider", "Payment provider"
    SUSPENSE = "suspense", "Suspense (unresolved/exception)"


class LedgerEntryImmutableError(Exception):
    pass


class LedgerEntry(TenantScopedModel):
    entry_type = models.CharField(max_length=32, choices=LedgerEntryType.choices, db_index=True)
    account = models.CharField(max_length=16, choices=LedgerAccount.choices)

    amount = models.DecimalField(**money_field_kwargs())
    currency = models.CharField(max_length=3, default="TZS")

    reference = models.CharField(max_length=100, blank=True, db_index=True)
    correlation_id = models.CharField(max_length=64, blank=True)

    # What this entry is about — a Payment, ControlNumber, Bill, or
    # SettlementBatch. Optional: some adjustments may not have one clean
    # source object.
    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.PROTECT)
    object_id = models.CharField(max_length=64, blank=True)
    source = GenericForeignKey("content_type", "object_id")

    # A compensating entry (refund/reversal/adjustment) points back at
    # the entry it corrects. The original entry is never touched.
    related_entry = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="compensating_entries"
    )

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["tenant", "entry_type", "created_at"]),
            models.Index(fields=["tenant", "account", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_entry_type_display()} {self.amount} {self.currency} ({self.account})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise LedgerEntryImmutableError("Ledger entries cannot be modified after creation.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerEntryImmutableError("Ledger entries cannot be deleted. Post a compensating entry instead.")
