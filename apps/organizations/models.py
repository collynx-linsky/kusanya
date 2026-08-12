"""
Sub-structure within a tenant: branches and departments.

Kept deliberately generic — a "branch" is a school campus, a hospital
site, a retail outlet, a hotel property, or a parish, depending on the
tenant's sector. Nothing here assumes any particular sector.
"""

from django.db import models

from apps.core.models import TenantScopedModel


class Branch(TenantScopedModel):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=32, blank=True)
    address = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_branch_name_per_tenant")
        ]
        ordering = ["tenant__name", "name"]

    def __str__(self):
        return f"{self.name} ({self.tenant.name})"


class Department(TenantScopedModel):
    branch = models.ForeignKey(
        Branch, null=True, blank=True, on_delete=models.CASCADE, related_name="departments"
    )
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_department_name_per_tenant")
        ]
        ordering = ["tenant__name", "name"]

    def __str__(self):
        return f"{self.name} ({self.tenant.name})"
