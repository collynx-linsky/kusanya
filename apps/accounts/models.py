"""
MFA — build spec section 28's "MFA-ready architecture," made real in
Phase 7. `MFADevice` is a User-level security concept, not tenant data —
a person's MFA setup doesn't belong to any one institution they might
have portal access to, so this inherits `BaseModel`, not
`TenantScopedModel`.
"""

import hashlib
import hmac

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.encoding import force_bytes

from apps.accounts.totp import generate_secret
from apps.core.models import BaseModel


def _backup_code_lookup_hash(raw_code: str) -> str:
    """HMAC-SHA256 keyed with SECRET_KEY, not PBKDF2/make_password.

    Backup codes are ~52 bits of `secrets`-sourced randomness (see
    mfa_services._generate_backup_code), not user-chosen passwords — the
    threat PBKDF2's deliberate slowness defends against (offline
    dictionary/brute-force search of a low-entropy secret) doesn't apply
    here. A keyed HMAC still satisfies "never store the raw code," is a
    genuine cryptographic MAC unforgeable without SECRET_KEY, and — unlike
    PBKDF2 — is cheap enough to use as an indexed exact-match lookup
    instead of a linear scan with a slow hash check per row. See
    ARCHITECTURE_DECISIONS ADR-027 and the Phase 7 report for the
    incident (a live-measured 18.7s rejection time) that prompted this.
    """
    normalized = raw_code.strip().upper()
    return hmac.new(force_bytes(settings.SECRET_KEY), normalized.encode("utf-8"), hashlib.sha256).hexdigest()


class MFADevice(BaseModel):
    """One TOTP device per user (this codebase doesn't support multiple
    concurrent authenticator apps per account — enabling MFA again while
    one exists is a UI no-op, see apps.accounts.portal_views)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mfa_device")
    secret = models.CharField(max_length=64, default=generate_secret, editable=False)
    confirmed = models.BooleanField(
        default=False,
        help_text="Not usable to log in until the user has proven they can generate a valid code.",
    )
    last_used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        status = "confirmed" if self.confirmed else "pending setup"
        return f"MFA device for {self.user.email} ({status})"


class BackupCode(BaseModel):
    """Single-use recovery codes, generated once when MFA is confirmed
    (build spec has no explicit backup-code requirement, but shipping MFA
    without a recovery path would lock users out of their own accounts
    the moment they lose their authenticator device — an unacceptable gap
    for a foundation meant to be taken seriously)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="backup_codes")
    lookup_hash = models.CharField(max_length=64, editable=False, db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "lookup_hash"])]

    def __str__(self):
        return f"Backup code for {self.user.email} ({'used' if self.used_at else 'unused'})"

    def set_code(self, raw_code: str) -> None:
        self.lookup_hash = _backup_code_lookup_hash(raw_code)

    def check_code(self, raw_code: str) -> bool:
        return hmac.compare_digest(self.lookup_hash, _backup_code_lookup_hash(raw_code))

    def mark_used(self) -> None:
        self.used_at = timezone.now()
        self.save(update_fields=["used_at", "updated_at"])
