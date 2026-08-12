"""
API credential lifecycle. See build spec section 23: "API credentials,
secret rotation." A raw secret is only ever available at the moment it's
generated (creation or rotation) — it is never stored, never displayed
again, and never recoverable. Losing it means generating a new one.
"""

from django.utils import timezone

from apps.api.models import ApiCredential, _generate_secret
from apps.audit.services import record_audit_event


def create_credential(*, tenant, name: str, actor=None) -> tuple[ApiCredential, str]:
    """Returns (credential, raw_secret). `raw_secret` must be shown to
    the caller exactly once — the credential itself only ever stores a
    hash (apps.api.models.ApiCredential.set_secret uses Django's own
    password hasher, the same primitive used for user passwords)."""
    raw_secret = _generate_secret()
    credential = ApiCredential(tenant=tenant, name=name, created_by=actor)
    credential.set_secret(raw_secret)
    credential.save()

    record_audit_event(
        action="api_credential.created", actor=actor, tenant=tenant, target=credential,
        metadata={"key_id": credential.key_id},
    )
    return credential, raw_secret


def rotate_credential(credential: ApiCredential, *, actor=None) -> str:
    """Immediate replacement, not a grace-period rotation: the old
    secret stops working the instant this returns. `key_id` (used to
    look the credential up) is unchanged — only the secret is replaced —
    so callers update one value, not their whole integration config.

    No overlap window is implemented. A real zero-downtime rotation
    would need the old secret to keep working for some period while the
    caller updates their config — deliberately not built in Phase 6; see
    ../ARCHITECTURE_DECISIONS.md for why this simpler behavior was
    chosen and what a caller needs to do to rotate safely without one."""
    raw_secret = _generate_secret()
    credential.set_secret(raw_secret)
    credential.save(update_fields=["secret_hash", "updated_at"])

    record_audit_event(
        action="api_credential.rotated", actor=actor, tenant=credential.tenant, target=credential,
        metadata={"key_id": credential.key_id},
    )
    return raw_secret


def revoke_credential(credential: ApiCredential, *, actor=None) -> ApiCredential:
    credential.is_active = False
    credential.revoked_at = timezone.now()
    credential.save(update_fields=["is_active", "revoked_at", "updated_at"])

    record_audit_event(
        action="api_credential.revoked", actor=actor, tenant=credential.tenant, target=credential,
        metadata={"key_id": credential.key_id},
    )
    return credential
