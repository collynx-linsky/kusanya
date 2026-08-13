"""
Reconciliation. See docs/RECONCILIATION_SPEC.md.

Scoped honestly to what's actually checkable given the provider
interface this codebase has (apps.providers.base.PaymentProviderAdapter):
per-reference comparison (`adapter.reconcile()`), not a bulk statement
import — see RECONCILIATION_SPEC.md for what that means this can and
can't detect.
"""

from django.db import models

from apps.core.encrypted_fields import EncryptedTextField
from apps.core.models import TenantScopedModel


class ReconciliationRunStatus(models.TextChoices):
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"


class ReconciliationRun(TenantScopedModel):
    status = models.CharField(
        max_length=16, choices=ReconciliationRunStatus.choices, default=ReconciliationRunStatus.RUNNING
    )
    triggered_by = models.ForeignKey(
        "users.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="reconciliation_runs"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    total_checked = models.PositiveIntegerField(default=0)
    matched_count = models.PositiveIntegerField(default=0)
    exception_count = models.PositiveIntegerField(default=0)
    resolved_unknown_count = models.PositiveIntegerField(
        default=0, help_text="UNKNOWN payments resolved to a final status during this run."
    )

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Reconciliation run {self.id} ({self.tenant.name}, {self.status})"


class ExceptionType(models.TextChoices):
    STUCK_UNKNOWN = "stuck_unknown", "Still UNKNOWN after querying the provider"
    STATUS_MISMATCH = "status_mismatch", "Internal status disagrees with the provider's"
    MISSING_AT_PROVIDER = "missing_at_provider", "Provider has no record of this reference"


class ExceptionStatus(models.TextChoices):
    OPEN = "open", "Open"
    RESOLVED = "resolved", "Resolved"


class ReconciliationException(TenantScopedModel):
    run = models.ForeignKey(
        ReconciliationRun, null=True, blank=True, on_delete=models.SET_NULL, related_name="exceptions"
    )
    payment = models.ForeignKey(
        "payments.Payment", on_delete=models.CASCADE, related_name="reconciliation_exceptions"
    )
    exception_type = models.CharField(max_length=32, choices=ExceptionType.choices)
    status = models.CharField(max_length=16, choices=ExceptionStatus.choices, default=ExceptionStatus.OPEN)

    details = models.JSONField(default=dict, blank=True)

    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        "users.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="reconciliation_exceptions_resolved"
    )
    # Encrypted at rest (ARCHITECTURE_DECISIONS ADR-032) — free text,
    # never externally serialized, no lookup_hash companion needed.
    resolution_notes = EncryptedTextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]

    def __str__(self):
        return f"{self.get_exception_type_display()} — {self.payment.merchant_reference} ({self.status})"
