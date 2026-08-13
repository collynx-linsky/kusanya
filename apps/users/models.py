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

from apps.core.encrypted_fields import EncryptedCharField, compute_lookup_hash
from apps.core.models import BaseModel
from apps.users.managers import UserManager


class User(AbstractUser):
    """Email-authenticated user. No username field.

    `email` is deliberately NOT encrypted — it's `USERNAME_FIELD`, has a
    DB-level `unique=True` constraint, and is looked up via exact match
    (`ModelBackend.get_by_natural_key`) on every single login. Encrypting
    it would need the same lookup_hash pattern used below for
    first_name/last_name, but the login path specifically needs a
    UNIQUE, database-enforced constraint — a lookup_hash column can
    support that too, but changing the field every login authenticates
    against is a materially higher-risk change than the fields below,
    and deserves its own dedicated review rather than being bundled in
    here. See ARCHITECTURE_DECISIONS ADR-032 for the full reasoning and
    this explicit deferral.

    `first_name`/`last_name` (overriding AbstractUser's plain
    CharFields, the same way `email` already overrides its parent) and
    `phone_number` are encrypted at rest.
    """

    username = None
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = EncryptedCharField(max_length=150, blank=True)
    first_name_lookup_hash = models.CharField(max_length=64, db_index=True, editable=False, blank=True, default="")
    last_name = EncryptedCharField(max_length=150, blank=True)
    last_name_lookup_hash = models.CharField(max_length=64, db_index=True, editable=False, blank=True, default="")
    phone_number = EncryptedCharField(max_length=32, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ["email"]

    def save(self, *args, **kwargs):
        self.first_name_lookup_hash = compute_lookup_hash(self.first_name) if self.first_name else ""
        self.last_name_lookup_hash = compute_lookup_hash(self.last_name) if self.last_name else ""
        super().save(*args, **kwargs)

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
