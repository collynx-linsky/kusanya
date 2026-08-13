"""MFA lifecycle. Backup codes follow the same "shown exactly once,
stored only as a hash" convention as API credential secrets
(apps.api.credential_services) and webhook signing secrets."""

import re
import secrets
import string

from apps.accounts.models import BackupCode, MFADevice
from apps.accounts.totp import verify_totp
from apps.audit.services import record_audit_event

BACKUP_CODE_COUNT = 10
_ALPHABET = string.ascii_uppercase + string.digits
_BACKUP_CODE_SHAPE = re.compile(r"^[A-Z0-9]{5}-[A-Z0-9]{5}$")


def _generate_backup_code() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(10))
    return f"{raw[:5]}-{raw[5:]}"


def _looks_like_backup_code(raw_code: str) -> bool:
    """Cheap shape check, run before touching the database at all.

    A mistyped 6-digit TOTP code is by far the most common failed-login
    input in practice — this rejects it in microseconds instead of
    querying/hashing against every unused backup code the user has.
    """
    return bool(_BACKUP_CODE_SHAPE.match(raw_code.strip().upper()))


def confirm_device(device: MFADevice, code: str, *, actor=None) -> bool:
    """Verifies the setup code and, on success, activates the device and
    issues a fresh set of backup codes. Returns False (no state changed)
    if the code doesn't verify — never partially activates a device."""
    if not verify_totp(device.secret, code):
        return False

    device.confirmed = True
    device.save(update_fields=["confirmed", "updated_at"])
    record_audit_event(action="mfa.enabled", actor=actor, target=device)
    return True


def generate_backup_codes(user, *, actor=None) -> list[str]:
    """Replaces any existing backup codes — issuing a new set invalidates
    the old ones, same "no silent duplication" spirit as credential
    rotation (ADR-024)."""
    BackupCode.objects.filter(user=user).delete()
    raw_codes = [_generate_backup_code() for _ in range(BACKUP_CODE_COUNT)]

    codes = []
    for raw in raw_codes:
        backup = BackupCode(user=user)
        backup.set_code(raw)
        codes.append(backup)
    BackupCode.objects.bulk_create(codes)

    record_audit_event(action="mfa.backup_codes_generated", actor=actor, target=None, metadata={"user": user.email})
    return raw_codes


def consume_backup_code(user, raw_code: str) -> bool:
    """O(1) indexed lookup, not a linear scan-and-hash over every unused
    code — see BackupCode._backup_code_lookup_hash for why an HMAC lookup
    hash (rather than the PBKDF2 make_password/check_password originally
    used here) is the right tool for a high-entropy random token."""
    if not raw_code or not _looks_like_backup_code(raw_code):
        return False

    from apps.accounts.models import _backup_code_lookup_hash

    lookup_hash = _backup_code_lookup_hash(raw_code)
    backup = BackupCode.objects.filter(
        user=user, lookup_hash=lookup_hash, used_at__isnull=True
    ).first()
    if backup is None:
        return False

    backup.mark_used()
    record_audit_event(action="mfa.backup_code_used", actor=user, target=backup)
    return True


def disable_mfa(user, *, actor=None) -> None:
    MFADevice.objects.filter(user=user).delete()
    BackupCode.objects.filter(user=user).delete()
    record_audit_event(action="mfa.disabled", actor=actor, target=None, metadata={"user": user.email})
