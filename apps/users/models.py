"""
Identity models.

`User` is KUSANYA's platform-wide identity — the same account a person
uses whether they're platform staff, a tenant's finance manager, or both.
"Which tenant(s) can this user act in, and as what role" lives in
apps.tenants.TenantMembership. "Does this user have a platform-level role"
lives here in PlatformMembership. Neither is derived from the other —
being staff at KUSANYA the company does not imply any tenant access, and
vice versa. See docs/RBAC.md.
"""

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.models import BaseModel
from apps.users.managers import UserManager


class User(AbstractUser):
    """Email-authenticated user. No username field."""

    username = None
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=32, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ["email"]

    def __str__(self):
        return self.email


class PlatformRole(models.TextChoices):
    """Platform-level (KUSANYA-the-company) roles — see build spec section 8.

    Distinct from tenant-level roles (apps.tenants.TenantRole). A user can
    hold platform roles, tenant roles, both, or neither.
    """

    SUPER_ADMIN = "super_admin", "Platform Super Administrator"
    FINANCE_ADMIN = "finance_admin", "Platform Finance Administrator"
    OPERATIONS_ADMIN = "operations_admin", "Platform Operations Administrator"
    COMPLIANCE_ADMIN = "compliance_admin", "Platform Compliance Administrator"
    SUPPORT_ADMIN = "support_admin", "Platform Support Administrator"
    AUDITOR = "auditor", "Platform Auditor"


class PlatformMembership(BaseModel):
    """Grants a user a platform-level role.

    Distinct from `User.is_staff`/`is_superuser` (Django's built-in admin
    site access flags). A user can be `is_staff` (can log into /admin/)
    without holding a specific PlatformRole, and — once finer-grained
    platform authorization is enforced outside /admin/ — could hold a
    PlatformRole for portal access without needing raw Django admin rights.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="platform_memberships")
    role = models.CharField(max_length=32, choices=PlatformRole.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="unique_user_platform_role")
        ]
        ordering = ["user__email", "role"]

    def __str__(self):
        return f"{self.user.email} · {self.get_role_display()}"
