"""
Reconciliation run logic. Two things happen in a run, matching build spec
section 17:

1. Every `UNKNOWN` payment gets an actual provider query attempted (this
   IS the "reconciliation is the backstop for UNKNOWN payments" promise
   from docs/PAYMENT_LIFECYCLE.md — it just reuses
   apps.payments.services.query_payment(), never re-implements it).
2. Every settled (SUCCESSFUL/FAILED) payment with a provider reference
   gets a consistency check against the provider's own `reconcile()`
   view of it. A mismatch NEVER silently auto-corrects the payment's
   status — it opens a `ReconciliationException` for a human to look at.
   Build spec section 4/16: never silently modify a settled financial
   event.
"""

from apps.payments.models import Payment, PaymentStatus
from apps.payments.services import OUTCOME_TO_STATUS, query_payment
from apps.providers.base import ProviderOutcome
from apps.providers.registry import get_adapter
from apps.reconciliation.models import (
    ExceptionStatus,
    ExceptionType,
    ReconciliationException,
    ReconciliationRun,
    ReconciliationRunStatus,
)


def run_reconciliation(*, tenant, actor=None) -> ReconciliationRun:
    run = ReconciliationRun.objects.create(tenant=tenant, triggered_by=actor)

    _resolve_unknown_payments(run, tenant=tenant, actor=actor)
    _check_settled_payments(run, tenant=tenant)

    run.status = ReconciliationRunStatus.COMPLETED
    from django.utils import timezone

    run.completed_at = timezone.now()
    run.save(update_fields=["status", "completed_at"])
    return run


def _resolve_unknown_payments(run: ReconciliationRun, *, tenant, actor=None) -> None:
    unknown_payments = Payment.objects.filter(tenant=tenant, status=PaymentStatus.UNKNOWN)
    for payment in unknown_payments:
        query_payment(payment, actor=actor)
        run.total_checked += 1
        if payment.status != PaymentStatus.UNKNOWN:
            run.resolved_unknown_count += 1
        else:
            ReconciliationException.objects.create(
                tenant=tenant,
                run=run,
                payment=payment,
                exception_type=ExceptionType.STUCK_UNKNOWN,
                details={"note": "Still UNKNOWN after querying the provider."},
            )
            run.exception_count += 1
    run.save(update_fields=["total_checked", "resolved_unknown_count", "exception_count"])


def _check_settled_payments(run: ReconciliationRun, *, tenant) -> None:
    settled = Payment.objects.filter(
        tenant=tenant, status__in=[PaymentStatus.SUCCESSFUL, PaymentStatus.FAILED]
    ).exclude(provider_reference="")

    for payment in settled:
        adapter = get_adapter(payment.provider)
        result = adapter.reconcile(provider_reference=payment.provider_reference)
        run.total_checked += 1

        if result.outcome == ProviderOutcome.UNKNOWN:
            ReconciliationException.objects.create(
                tenant=tenant,
                run=run,
                payment=payment,
                exception_type=ExceptionType.MISSING_AT_PROVIDER,
                details={"internal_status": payment.status},
            )
            run.exception_count += 1
            continue

        expected_status = OUTCOME_TO_STATUS.get(result.outcome)
        if expected_status != payment.status:
            ReconciliationException.objects.create(
                tenant=tenant,
                run=run,
                payment=payment,
                exception_type=ExceptionType.STATUS_MISMATCH,
                details={
                    "internal_status": payment.status,
                    "provider_outcome": result.outcome.value,
                },
            )
            run.exception_count += 1
        else:
            run.matched_count += 1

    run.save(update_fields=["total_checked", "matched_count", "exception_count"])


def resolve_exception(exception: ReconciliationException, *, actor, notes: str = "") -> ReconciliationException:
    from django.utils import timezone

    from apps.audit.services import record_audit_event

    exception.status = ExceptionStatus.RESOLVED
    exception.resolved_at = timezone.now()
    exception.resolved_by = actor
    exception.resolution_notes = notes
    exception.save(update_fields=["status", "resolved_at", "resolved_by", "resolution_notes", "updated_at"])
    record_audit_event(
        action="reconciliation.exception_resolved", actor=actor, tenant=exception.tenant, target=exception
    )
    return exception
