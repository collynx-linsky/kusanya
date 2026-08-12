"""Single entry point application code uses to write an audit record.

Prefer this over `AuditLog.objects.create(...)` directly — it fills in
request context (IP/user agent/correlation ID) automatically and keeps the
"how do we audit something" decision in one place.
"""

from apps.audit.context import get_request_context
from apps.audit.models import AuditLog
from apps.core.correlation import get_correlation_id


def record_audit_event(
    *,
    action: str,
    actor=None,
    tenant=None,
    target=None,
    before: dict | None = None,
    after: dict | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    request_context = get_request_context()

    return AuditLog.objects.create(
        action=action,
        actor=actor,
        tenant=tenant,
        content_type=None if target is None else _content_type_for(target),
        object_id="" if target is None else str(target.pk),
        before=before,
        after=after,
        metadata=metadata or {},
        ip_address=request_context.get("ip_address"),
        user_agent=request_context.get("user_agent", ""),
        correlation_id=get_correlation_id(),
    )


def _content_type_for(target):
    from django.contrib.contenttypes.models import ContentType

    return ContentType.objects.get_for_model(target)
