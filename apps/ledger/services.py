"""Single entry point for writing to the ledger. Application code never
constructs a LedgerEntry directly — this fills in correlation ID
consistently and keeps "how do we post a ledger entry" in one place, the
same rationale as apps.audit.services.record_audit_event."""

from apps.core.correlation import get_correlation_id
from apps.ledger.models import LedgerEntry


def post_entry(
    *,
    tenant,
    entry_type: str,
    account: str,
    amount,
    currency: str = "TZS",
    reference: str = "",
    source=None,
    related_entry: LedgerEntry | None = None,
    metadata: dict | None = None,
) -> LedgerEntry:
    return LedgerEntry.objects.create(
        tenant=tenant,
        entry_type=entry_type,
        account=account,
        amount=amount,
        currency=currency,
        reference=reference,
        correlation_id=get_correlation_id(),
        content_type=None if source is None else _content_type_for(source),
        object_id="" if source is None else str(source.pk),
        related_entry=related_entry,
        metadata=metadata or {},
    )


def post_compensating_entry(
    *, original: LedgerEntry, entry_type: str, amount, metadata: dict | None = None
) -> LedgerEntry:
    """A compensating entry always inherits the original's tenant,
    account, currency, and reference — only the type, amount (typically
    negated), and metadata differ. Never mutates `original`."""
    return post_entry(
        tenant=original.tenant,
        entry_type=entry_type,
        account=original.account,
        amount=amount,
        currency=original.currency,
        reference=original.reference,
        source=original.source,
        related_entry=original,
        metadata=metadata or {},
    )


def _content_type_for(obj):
    from django.contrib.contenttypes.models import ContentType

    return ContentType.objects.get_for_model(obj)
