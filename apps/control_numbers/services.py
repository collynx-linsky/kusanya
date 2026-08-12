"""
The control-number engine's one real rule, enforced here and only here:
requesting a control number for a bill/account that already has an active
one returns the existing one — it never creates a second. This is what
docs/PRICING_MODEL.md's fee rule (Phase 4) will key off of, and it's
already true and tested independently of whether any fee is ever charged.

Callers should always use `get_or_create_for_bill` /
`get_or_create_for_account`, never construct a `ControlNumber` directly —
the atomicity of "check, then create" lives here.
"""

import random

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import record_audit_event
from apps.control_numbers.models import ControlNumber, ControlNumberScope, ControlNumberStatus

_MAX_GENERATION_ATTEMPTS = 5


def generate_value() -> str:
    """Date-prefixed, collision-resistant, PII-free.

    Format: YYMMDD + 6 random digits (e.g. "260812384729"), matching the
    shape of the example in the build spec. Global uniqueness is enforced
    at the database level (ControlNumber.value is unique=True) — this
    function does not itself guarantee uniqueness, callers must handle
    IntegrityError on insert (see get_or_create_for_bill/_account below).
    """
    prefix = timezone.now().strftime("%y%m%d")
    suffix = f"{random.randint(0, 999_999):06d}"
    return f"{prefix}{suffix}"


def get_or_create_for_bill(*, tenant, bill, actor=None, expires_at=None):
    """One-time control number bound to a single bill."""
    existing = ControlNumber.objects.filter(bill=bill).first()
    if existing is not None:
        record_audit_event(
            action="control_number.reused", actor=actor, tenant=tenant, target=existing
        )
        return existing, False

    for _attempt in range(_MAX_GENERATION_ATTEMPTS):
        try:
            with transaction.atomic():
                control_number = ControlNumber.objects.create(
                    tenant=tenant,
                    bill=bill,
                    scope=ControlNumberScope.ONE_TIME,
                    value=generate_value(),
                    created_by=actor,
                    expires_at=expires_at,
                )
                record_audit_event(
                    action="control_number.created",
                    actor=actor,
                    tenant=tenant,
                    target=control_number,
                )
            return control_number, True
        except IntegrityError:
            # Either a `value` collision (retry with a fresh value) or a
            # concurrent request for the same bill won the race on the
            # bill OneToOneField (in which case return what it created).
            existing = ControlNumber.objects.filter(bill=bill).first()
            if existing is not None:
                return existing, False
            continue

    raise IntegrityError("Could not generate a unique control number after several attempts.")


def get_or_create_for_account(*, tenant, customer_account, actor=None, expires_at=None):
    """Persistent control number bound to a customer account. Reused
    across every bill raised against that account until it expires or is
    cancelled, at which point a fresh one may be issued."""
    existing = ControlNumber.objects.filter(
        customer_account=customer_account, status=ControlNumberStatus.ACTIVE
    ).first()
    if existing is not None:
        record_audit_event(
            action="control_number.reused", actor=actor, tenant=tenant, target=existing
        )
        return existing, False

    for _attempt in range(_MAX_GENERATION_ATTEMPTS):
        try:
            with transaction.atomic():
                control_number = ControlNumber.objects.create(
                    tenant=tenant,
                    customer_account=customer_account,
                    scope=ControlNumberScope.PERSISTENT,
                    value=generate_value(),
                    created_by=actor,
                    expires_at=expires_at,
                )
                record_audit_event(
                    action="control_number.created",
                    actor=actor,
                    tenant=tenant,
                    target=control_number,
                )
            return control_number, True
        except IntegrityError:
            existing = ControlNumber.objects.filter(
                customer_account=customer_account, status=ControlNumberStatus.ACTIVE
            ).first()
            if existing is not None:
                return existing, False
            continue

    raise IntegrityError("Could not generate a unique control number after several attempts.")


def cancel(control_number: ControlNumber, *, actor=None):
    control_number.status = ControlNumberStatus.CANCELLED
    control_number.cancelled_at = timezone.now()
    control_number.save(update_fields=["status", "cancelled_at", "updated_at"])
    record_audit_event(
        action="control_number.cancelled",
        actor=actor,
        tenant=control_number.tenant,
        target=control_number,
    )
    return control_number


def expire_overdue(*, tenant=None) -> int:
    """Marks any ACTIVE control number past its `expires_at` as EXPIRED.
    Intended to be called from a scheduled Celery task once one exists
    (Phase 3+) — not wired to Celery beat yet in Phase 2, since nothing
    else in the platform depends on expiry timing yet."""
    qs = ControlNumber.objects.filter(
        status=ControlNumberStatus.ACTIVE, expires_at__isnull=False, expires_at__lt=timezone.now()
    )
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    count = qs.update(status=ControlNumberStatus.EXPIRED, updated_at=timezone.now())
    return count
