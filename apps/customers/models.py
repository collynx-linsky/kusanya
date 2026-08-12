"""
Customer + CustomerAccount — the universal payer-side entities every bill
and control number ultimately belongs to.

Deliberately sector-neutral: a `Customer` is whoever a tenant bills — a
parent paying school fees, a patient paying a clinic, a tenant paying
rent, a member paying a subscription. Sector-specific identifiers
(student ID, patient ID, lease ID, ...) live in `metadata`, never as
bespoke columns — see docs/PRODUCT_REQUIREMENTS.md#universal-data-model.
"""

from django.db import models

from apps.core.models import TenantScopedModel


class Customer(TenantScopedModel):
    """A person or organization a tenant bills.

    `full_name` is a single field rather than first/last — some tenants
    bill organizations (a company paying a training institution) as a
    "customer," where first/last name doesn't apply.
    """

    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone_number = models.CharField(max_length=32, blank=True)

    # Set by the caller (typically an ERP integration, Phase 6) to make
    # customer creation idempotent — see apps.customers.services.
    external_reference = models.CharField(max_length=100, blank=True)

    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "external_reference"],
                condition=models.Q(external_reference__gt=""),
                name="unique_customer_external_reference_per_tenant",
            )
        ]

    def __str__(self):
        return self.full_name


class CustomerAccount(TenantScopedModel):
    """A billing relationship for a customer — e.g. "ABC School — Academic
    Year 2026/2027", "Unit 4B — Monthly Rent", "Membership — 2026".

    One customer can have multiple accounts (a parent with two children at
    the same school; a tenant with two leased units). Bills and persistent
    control numbers attach to an account, not directly to a customer, so a
    customer with multiple concurrent billing relationships doesn't have
    them conflated into one balance.
    """

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="accounts")
    revenue_source = models.ForeignKey(
        "billing.RevenueSource",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="customer_accounts",
    )
    name = models.CharField(max_length=255)
    external_reference = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["customer__full_name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "external_reference"],
                condition=models.Q(external_reference__gt=""),
                name="unique_account_external_reference_per_tenant",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.customer.full_name})"
