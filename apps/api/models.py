"""
External API credentials. See docs/API_ARCHITECTURE.md and build spec
section 23.

An `ApiCredential` is what an external system (ERP, POS, hospital/hotel
system) authenticates the KUSANYA API with — it is deliberately NOT a
Django `User`: an integration isn't a person, doesn't log into the
portal, and shouldn't be representable via the session-based auth stack
at all. See ../ARCHITECTURE_DECISIONS.md for why.
"""

import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone

from apps.core.models import TenantScopedModel


def _generate_key_id() -> str:
    return f"kusanya_{secrets.token_hex(12)}"


def _generate_secret() -> str:
    return secrets.token_urlsafe(32)


class ApiCredential(TenantScopedModel):
    key_id = models.CharField(max_length=64, unique=True, default=_generate_key_id, editable=False)
    secret_hash = models.CharField(max_length=255, editable=False)

    name = models.CharField(max_length=150, help_text="What this credential is for, e.g. \"School ERP integration\".")
    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        "users.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="api_credentials_created"
    )
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["tenant__name", "name"]

    def __str__(self):
        status = "active" if self.is_active else "revoked"
        return f"{self.name} ({self.key_id}, {status})"

    def set_secret(self, raw_secret: str) -> None:
        self.secret_hash = make_password(raw_secret)

    def check_secret(self, raw_secret: str) -> bool:
        return check_password(raw_secret, self.secret_hash)

    def mark_used(self) -> None:
        # A lightweight, best-effort timestamp update — not wrapped in
        # request-audit machinery, since every authenticated API call
        # would otherwise write an audit row just for showing up.
        ApiCredential.objects.filter(pk=self.pk).update(last_used_at=timezone.now())
