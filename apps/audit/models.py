"""
Immutable, hash-chained audit log.

Every audit record includes the SHA-256 hash of the previous record, so
altering or deleting a historical row breaks the chain for every record
after it — detectable by re-walking the chain and recomputing hashes.

Honesty check on what this does and doesn't guarantee: this is an
in-database, application-level chain, not a cryptographically signed or
externally-anchored one. Someone with direct database write access (e.g. a
compromised superuser DB credential) could recompute the whole chain
after tampering and it would look consistent again. Real tamper-evidence
for a regulated financial platform additionally needs write-only DB
permissions for the app role, off-box log shipping, and/or periodic
external anchoring — tracked as follow-up, not implemented in Phase 1. See
docs/SECURITY_ARCHITECTURE.md.

Known concurrency limitation: computing `previous_hash` reads the latest
row and writes a new one without a serializing lock, so two audit events
committed at the exact same instant on different DB connections could each
compute the same `previous_hash` and both link to the same predecessor
(a fork rather than a broken chain). Acceptable for Phase 1's write volume;
revisit with a DB advisory lock (or a single audit-writer queue) before
this is under concurrent production load.
"""

import hashlib
import json
import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

GENESIS_HASH = "0" * 64


class AuditLogImmutableError(Exception):
    """Raised when code attempts to update or delete an existing audit record."""


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
        help_text="Null for system-initiated actions (e.g. scheduled jobs).",
    )
    actor_label = models.CharField(
        max_length=255,
        blank=True,
        help_text="Human-readable actor snapshot, kept even if the user is later deleted.",
    )

    tenant = models.ForeignKey(
        "tenants.Tenant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
        help_text="Null for platform-level events with no single tenant.",
    )

    action = models.CharField(max_length=100, db_index=True, help_text='e.g. "tenant.approved"')

    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.CharField(max_length=64, blank=True)
    target = GenericForeignKey("content_type", "object_id")

    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    correlation_id = models.CharField(max_length=64, blank=True, db_index=True)

    previous_hash = models.CharField(max_length=64, editable=False)
    record_hash = models.CharField(max_length=64, unique=True, editable=False, db_index=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]

    def __str__(self):
        return f"[{self.created_at:%Y-%m-%d %H:%M:%S}] {self.action} by {self.actor_label or 'system'}"

    def _canonical_payload(self) -> str:
        # `actor_label`, not `actor_id` -- ADR-035. `actor` is
        # on_delete=SET_NULL: deleting a user who ever performed an
        # audited action silently nulls `actor_id` on every one of
        # their historical records. Hashing that live, mutable FK value
        # meant an ordinary user deletion permanently broke chain
        # verification for records that were never actually tampered
        # with -- a real false positive, found live (ADR-035 has the
        # full story). `actor_label` is the field this model already
        # snapshots specifically to survive actor deletion (see its own
        # help_text) and, unlike `actor_id`, never changes after
        # creation -- the correct value to hash. `tenant_id` has the
        # same SET_NULL shape and isn't fixed here; tenants are never
        # hard-deleted by any code path in this system (suspended, not
        # removed), so it's a real but effectively unreachable risk,
        # not a demonstrated one -- see ADR-035.
        payload = {
            "action": self.action,
            "actor_label": self.actor_label or None,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "content_type_id": self.content_type_id,
            "object_id": self.object_id,
            "before": self.before,
            "after": self.after,
            "metadata": self.metadata,
            "correlation_id": self.correlation_id,
            "created_at": self.created_at.isoformat(),
        }
        return json.dumps(payload, sort_keys=True, default=str)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditLogImmutableError("Audit log records cannot be modified after creation.")

        if self.actor_id and not self.actor_label:
            self.actor_label = str(self.actor)

        last = AuditLog.objects.order_by("-created_at", "-id").first()
        self.previous_hash = last.record_hash if last else GENESIS_HASH
        self.record_hash = hashlib.sha256(
            f"{self.previous_hash}:{self._canonical_payload()}".encode("utf-8")
        ).hexdigest()

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditLogImmutableError("Audit log records cannot be deleted.")

    @classmethod
    def verify_chain(cls, queryset=None) -> tuple[bool, "AuditLog | None"]:
        """Recomputes the hash chain and returns (is_intact, first_broken_record)."""
        qs = (queryset or cls.objects.all()).order_by("created_at", "id")
        expected_previous = GENESIS_HASH
        for record in qs.iterator():
            if record.previous_hash != expected_previous:
                return False, record
            recomputed = hashlib.sha256(
                f"{record.previous_hash}:{record._canonical_payload()}".encode("utf-8")
            ).hexdigest()
            if recomputed != record.record_hash:
                return False, record
            expected_previous = record.record_hash
        return True, None
