from decimal import Decimal

import pytest
from django.utils import timezone

from apps.payments.services import initiate_payment
from apps.settlement.models import SettlementStatus
from apps.settlement.services import generate_settlement_batch, mark_settlement_completed


@pytest.mark.django_db
class TestSettlementBatchGeneration:
    def _make_payment(self, tenant, mock_provider, make_bill_with_control_number, amount=Decimal("100000")):
        bill, control_number = make_bill_with_control_number(tenant, amount=amount)
        return initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider, amount=amount
        )

    def test_batch_includes_successful_payments_and_computes_net_correctly(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        start = timezone.now() - timezone.timedelta(days=1)
        p1 = self._make_payment(tenant, mock_provider, make_bill_with_control_number, Decimal("100000"))
        p2 = self._make_payment(tenant, mock_provider, make_bill_with_control_number, Decimal("200000"))
        end = timezone.now() + timezone.timedelta(days=1)

        batch = generate_settlement_batch(
            tenant=tenant, provider=mock_provider, period_start=start, period_end=end
        )

        assert batch.gross_amount == Decimal("300000.00")
        assert batch.platform_fee_total == Decimal("100.00")  # 2 x TZS 50
        assert batch.provider_fee_total == Decimal("0.00")  # mock charges nothing
        assert batch.net_amount == Decimal("299900.00")
        assert batch.payments.count() == 2

        p1.refresh_from_db()
        p2.refresh_from_db()
        assert p1.settlement_batch_id == batch.id
        assert p2.settlement_batch_id == batch.id

    def test_a_payment_is_never_settled_twice(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        start = timezone.now() - timezone.timedelta(days=1)
        self._make_payment(tenant, mock_provider, make_bill_with_control_number, Decimal("50000"))
        end = timezone.now() + timezone.timedelta(days=1)

        first_batch = generate_settlement_batch(
            tenant=tenant, provider=mock_provider, period_start=start, period_end=end
        )
        second_batch = generate_settlement_batch(
            tenant=tenant, provider=mock_provider, period_start=start, period_end=end
        )

        assert first_batch.payments.count() == 1
        assert second_batch.payments.count() == 0  # already claimed by the first batch
        assert second_batch.gross_amount == Decimal("0.00")

    def test_failed_and_pending_payments_are_excluded(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        start = timezone.now() - timezone.timedelta(days=1)
        bill, control_number = make_bill_with_control_number(tenant)
        initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider,
            amount=Decimal("1000"), metadata={"mock_outcome": "failed"},
        )
        end = timezone.now() + timezone.timedelta(days=1)

        batch = generate_settlement_batch(
            tenant=tenant, provider=mock_provider, period_start=start, period_end=end
        )

        assert batch.payments.count() == 0
        assert batch.gross_amount == Decimal("0.00")


@pytest.mark.django_db
class TestSettlementCompletion:
    def test_marking_completed_sets_status_and_reference(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        tenant = make_tenant()
        start = timezone.now() - timezone.timedelta(days=1)
        bill, control_number = make_bill_with_control_number(tenant)
        initiate_payment(tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("1000"))
        end = timezone.now() + timezone.timedelta(days=1)
        batch = generate_settlement_batch(tenant=tenant, provider=mock_provider, period_start=start, period_end=end)

        mark_settlement_completed(batch, external_settlement_reference="BANK-REF-XYZ")

        batch.refresh_from_db()
        assert batch.status == SettlementStatus.COMPLETED
        assert batch.external_settlement_reference == "BANK-REF-XYZ"
        assert batch.settlement_date is not None

    def test_completion_dispatches_a_webhook(
        self, make_tenant, make_bill_with_control_number, mock_provider
    ):
        """apps.webhooks.services.dispatch_event creates the
        WebhookDelivery row synchronously — only the Celery `.delay()`
        enqueue (and the actual HTTP call) is deferred via
        transaction.on_commit (see ARCHITECTURE_DECISIONS ADR-015). That
        deferred half, plus signing/retry/dead-letter, is already covered
        by apps/webhooks/tests/tests.py; this test only needs to confirm
        settlement completion triggers the dispatch in the first place,
        which doesn't require a real commit to observe."""
        from apps.webhooks.models import WebhookDelivery, WebhookEndpoint

        tenant = make_tenant()
        WebhookEndpoint.objects.create(tenant=tenant, url="https://erp.example.com/hook")

        start = timezone.now() - timezone.timedelta(days=1)
        bill, control_number = make_bill_with_control_number(tenant)
        initiate_payment(tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("1000"))
        end = timezone.now() + timezone.timedelta(days=1)
        batch = generate_settlement_batch(tenant=tenant, provider=mock_provider, period_start=start, period_end=end)
        mark_settlement_completed(batch, external_settlement_reference="BANK-REF-1")

        assert WebhookDelivery.objects.filter(tenant=tenant, event_type="settlement.completed").exists()
