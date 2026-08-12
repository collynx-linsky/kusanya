"""
Settlement batch generation and completion. See models.py's module
docstring for the regulatory framing this must respect: KUSANYA records
settlement, it does not perform the funds movement itself.
"""

from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.audit.services import record_audit_event
from apps.payments.models import Payment, PaymentStatus
from apps.revenue.models import RevenueEvent, RevenueEventType
from apps.settlement.models import SettlementBatch, SettlementStatus
from apps.webhooks.services import dispatch_event


def generate_settlement_batch(*, tenant, provider, period_start, period_end, actor=None) -> SettlementBatch:
    """Includes every SUCCESSFUL payment for this tenant/provider in the
    period that hasn't already been settled (`settlement_batch is null`)
    — a payment is settled at most once, enforced by only ever selecting
    unsettled payments and atomically claiming them into this batch."""
    with transaction.atomic():
        payments = list(
            Payment.objects.select_for_update()
            .filter(
                tenant=tenant,
                provider=provider,
                status=PaymentStatus.SUCCESSFUL,
                settlement_batch__isnull=True,
                completed_at__gte=period_start,
                completed_at__lt=period_end,
            )
        )

        gross_amount = sum((p.amount for p in payments), Decimal("0"))

        platform_fee_total = (
            RevenueEvent.objects.filter(
                tenant=tenant,
                event_type=RevenueEventType.PAYMENT_SUCCESSFUL,
                content_type=ContentType.objects.get_for_model(Payment),
                object_id__in=[str(p.id) for p in payments],
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )

        # No real provider is integrated (see docs/PAYMENT_PROVIDER_ARCHITECTURE.md)
        # — the mock provider charges nothing, so this is always 0 today.
        # The field exists so a real adapter's fee schedule has somewhere
        # to be recorded once one exists.
        provider_fee_total = Decimal("0")

        net_amount = gross_amount - platform_fee_total - provider_fee_total

        batch = SettlementBatch.objects.create(
            tenant=tenant,
            provider=provider,
            period_start=period_start,
            period_end=period_end,
            gross_amount=gross_amount,
            platform_fee_total=platform_fee_total,
            provider_fee_total=provider_fee_total,
            net_amount=net_amount,
            currency=tenant.default_currency,
        )

        Payment.objects.filter(id__in=[p.id for p in payments]).update(settlement_batch=batch)

        record_audit_event(
            action="settlement.batch_created",
            actor=actor,
            tenant=tenant,
            target=batch,
            after={
                "gross_amount": str(gross_amount),
                "net_amount": str(net_amount),
                "payment_count": len(payments),
            },
        )

    return batch


def mark_settlement_completed(
    batch: SettlementBatch, *, external_settlement_reference: str, actor=None
) -> SettlementBatch:
    """Records that the licensed provider/bank has confirmed the actual
    funds transfer — KUSANYA does not and cannot cause this transfer
    itself. See docs/compliance/REGULATORY_ASSUMPTIONS.md."""
    batch.status = SettlementStatus.COMPLETED
    batch.settlement_date = timezone.now()
    batch.external_settlement_reference = external_settlement_reference
    batch.save(update_fields=["status", "settlement_date", "external_settlement_reference", "updated_at"])

    record_audit_event(action="settlement.completed", actor=actor, tenant=batch.tenant, target=batch)
    dispatch_event(
        tenant=batch.tenant,
        event_type="settlement.completed",
        payload={
            "settlement_batch_id": str(batch.id),
            "reference": batch.reference,
            "net_amount": str(batch.net_amount),
            "currency": batch.currency,
            "external_settlement_reference": external_settlement_reference,
        },
    )
    return batch
