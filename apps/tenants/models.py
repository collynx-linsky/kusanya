"""
Tenant + tenant-membership models — the multi-tenancy foundation.

A Tenant is any institution/business using KUSANYA. Sector is metadata,
never a switch that changes core billing/payment behaviour (see
docs/MULTI_TENANCY.md and the build spec's "universal data model" section).
Sector-specific fields belong in each domain record's `metadata` JSONField
once billing exists (Phase 2+), not as extra columns on Tenant.
"""

from django.conf import settings
from django.db import models
from django.utils.text import slugify

from apps.core.encrypted_fields import EncryptedCharField, compute_lookup_hash
from apps.core.models import BaseModel


class Sector(models.TextChoices):
    """Informational only. Never branches core payment/billing logic."""

    EDUCATION = "education", "Education"
    HEALTHCARE = "healthcare", "Healthcare"
    RETAIL = "retail", "Retail"
    HOSPITALITY = "hospitality", "Hospitality"
    PROPERTY = "property", "Property management"
    PROFESSIONAL_SERVICES = "professional_services", "Professional services"
    NGO = "ngo", "NGO"
    RELIGIOUS = "religious", "Religious organization"
    TRAINING = "training", "Training institution"
    MEMBERSHIP = "membership", "Membership organization"
    UTILITIES = "utilities", "Utilities"
    ASSOCIATION = "association", "Association"
    GOVERNMENT_ADJACENT = "government_adjacent", "Government-adjacent / private institution"
    OTHER = "other", "Other"


class Tenant(BaseModel):
    """An institution or business using KUSANYA."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending approval"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        REJECTED = "rejected", "Rejected"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    sector = models.CharField(max_length=32, choices=Sector.choices, default=Sector.OTHER)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    # Encrypted at rest (ARCHITECTURE_DECISIONS ADR-032). contact_email
    # has a lookup_hash companion (it's admin-searched); contact_phone
    # doesn't need one (it isn't).
    contact_email = EncryptedCharField(max_length=254)
    contact_email_lookup_hash = models.CharField(max_length=64, db_index=True, editable=False, default="")
    contact_phone = EncryptedCharField(max_length=32, blank=True)

    default_currency = models.CharField(max_length=3, default="TZS")

    class FeeRefundPolicy(models.TextChoices):
        CLAWBACK = "clawback", "Claw back platform fee on refund/reversal"
        RETAIN = "retain", "Retain platform fee on refund/reversal"

    # Build spec section 4: reversal/refund accounting treatment "must
    # have configurable accounting treatment" — this is that
    # configuration point. Read by apps.revenue.services; see
    # docs/PRICING_MODEL.md#reversal--refund-accounting-treatment.
    fee_refund_policy = models.CharField(
        max_length=16, choices=FeeRefundPolicy.choices, default=FeeRefundPolicy.CLAWBACK
    )

    # Sector-specific configuration lives here rather than as bespoke
    # columns — e.g. {"academic_year_label": "2026/2027"} for a school,
    # {"department_list": [...]} for a hospital. The core engine never
    # reads this key-by-key; it is opaque passthrough for the tenant's own
    # apps/reports/templates.
    metadata = models.JSONField(default=dict, blank=True)

    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tenants_approved",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:220]
        self.contact_email_lookup_hash = compute_lookup_hash(self.contact_email.lower())
        super().save(*args, **kwargs)


class TenantRole(models.TextChoices):
    """Tenant-level roles — see build spec section 8."""

    ADMIN = "tenant_admin", "Tenant Administrator"
    FINANCE_MANAGER = "finance_manager", "Finance Manager"
    ACCOUNTANT = "accountant", "Accountant"
    BILLING_OFFICER = "billing_officer", "Billing Officer"
    RECONCILIATION_OFFICER = "reconciliation_officer", "Reconciliation Officer"
    VIEWER = "viewer", "Viewer"
    API_CLIENT = "api_client", "API Client"


class TenantMembership(BaseModel):
    """Grants a user a role within a specific tenant.

    This is the join point tenant isolation is built on: a user's access to
    tenant-owned data is always mediated through an active membership row,
    never through a tenant ID the client supplied directly. See
    apps.tenants.middleware.TenantResolutionMiddleware and
    docs/MULTI_TENANCY.md.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tenant_memberships"
    )
    role = models.CharField(max_length=32, choices=TenantRole.choices)
    is_active = models.BooleanField(default=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tenant_invitations_sent",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "user"], name="unique_tenant_user_membership")
        ]
        ordering = ["tenant__name", "user__email"]

    def __str__(self):
        return f"{self.user.email} @ {self.tenant.name} ({self.get_role_display()})"
