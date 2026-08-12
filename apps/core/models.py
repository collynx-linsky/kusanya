"""
Abstract base models shared across every KUSANYA domain app.

These are intentionally sector-neutral and contain no billing/payment
concepts — they exist so every future domain model gets a UUID identity,
timestamps, and (where relevant) tenant scoping for free and consistently.
"""

import uuid

from django.db import models


class BaseModel(models.Model):
    """Common identity + audit-timestamp fields for every KUSANYA record.

    UUID primary keys are used platform-wide (see ARCHITECTURE_DECISIONS.md)
    so identifiers are safe to expose externally (APIs, webhooks, receipts)
    without leaking sequential/guessable database row counts.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        get_latest_by = "created_at"


class TenantScopedModel(BaseModel):
    """Base for every model that belongs to exactly one tenant.

    Any domain model holding tenant-owned data (customers, bills, payments,
    etc.) must inherit from this rather than adding an ad-hoc `tenant`
    FK — this keeps tenant-isolation enforcement (see apps.tenants) and
    querysets consistent across the whole codebase. See
    docs/MULTI_TENANCY.md.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_set",
    )

    class Meta:
        abstract = True

# Note: no soft-delete mixin is defined yet. Financial records must never be
# silently deleted (see ARCHITECTURE_DECISIONS.md, "Immutable financial
# events"), but the correction mechanism for those apps is compensating
# ledger entries, not row-level soft-delete — a generic soft-delete mixin
# would invite the wrong pattern. Non-financial tenant data that needs
# soft-delete can add its own `deleted_at` field when that need arises.
