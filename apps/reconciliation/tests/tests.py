from decimal import Decimal

import pytest

from apps.payments.models import PaymentStatus
from apps.payments.services import initiate_payment
from apps.providers.models import MockProviderTransaction
from apps.reconciliation.models import ExceptionStatus, ExceptionType, ReconciliationException
from apps.reconciliation.services import resolve_exception, run_reconciliation


@pytest.mark.django_db
class TestReconciliationResolvesUnknownPayments:
    def test_run_resolves_a_stale_unknown_payment(
        self, make_tenant, make_bill_with_control_number, mock_provider, make_user
    ):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("500000"))
        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider,
            amount=Decimal("500000"), metadata={"mock_outcome": "timeout"},
        )
        assert payment.status == PaymentStatus.UNKNOWN

        run = run_reconciliation(tenant=tenant, actor=make_user())

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.SUCCESSFUL
        assert run.resolved_unknown_count == 1
        assert run.exception_count == 0

    def test_run_opens_an_exception_if_still_unknown_after_query(
        self, make_tenant, make_customer, make_customer_account, mock_provider, make_user
    ):
        """A payment that's UNKNOWN because it was never actually
        initiated at the provider (no MockProviderTransaction row at
        all) stays UNKNOWN even after querying — reconciliation must
        flag that, not silently ignore it."""
        from apps.billing.models import BillStatus
        from apps.billing.services import get_or_create_bill
        from apps.control_numbers.services import get_or_create_for_bill
        from apps.payments.models import Payment

        tenant = make_tenant()
        customer = make_customer(tenant)
        account = make_customer_account(tenant, customer)
        bill, _ = get_or_create_bill(
            tenant=tenant, customer_account=account, items=[{"description": "Fee", "unit_amount": Decimal("100")}]
        )
        bill.transition_to(BillStatus.ACTIVE)
        control_number, _ = get_or_create_for_bill(tenant=tenant, bill=bill)

        # A payment stuck UNKNOWN with no corresponding provider record
        # at all (simulates a request that never reached the provider).
        stuck_payment = Payment.objects.create(
            tenant=tenant, control_number=control_number, provider=mock_provider,
            amount=Decimal("100"), currency="TZS", status=PaymentStatus.UNKNOWN,
            merchant_reference="STUCK-REF-1",
        )

        run = run_reconciliation(tenant=tenant, actor=make_user())

        stuck_payment.refresh_from_db()
        assert stuck_payment.status == PaymentStatus.UNKNOWN
        assert run.exception_count == 1
        exception = ReconciliationException.objects.get(payment=stuck_payment)
        assert exception.exception_type == ExceptionType.STUCK_UNKNOWN


@pytest.mark.django_db
class TestReconciliationDetectsDrift:
    def test_status_mismatch_is_flagged_not_silently_corrected(
        self, make_tenant, make_bill_with_control_number, mock_provider, make_user
    ):
        """Simulates real-world drift: KUSANYA recorded SUCCESSFUL, but
        the provider's own record has since changed (e.g. a chargeback
        processed on the provider's side outside KUSANYA's knowledge).
        Reconciliation must surface this as an exception, never silently
        flip the payment's already-settled status."""
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("1000"))
        payment = initiate_payment(
            tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("1000"),
        )
        assert payment.status == PaymentStatus.SUCCESSFUL

        # Simulate provider-side drift directly on the mock's own record.
        txn = MockProviderTransaction.objects.get(provider_reference=payment.provider_reference)
        txn.outcome = "failed"
        txn.save(update_fields=["outcome"])

        run = run_reconciliation(tenant=tenant, actor=make_user())

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.SUCCESSFUL  # NOT silently changed
        assert run.exception_count == 1
        exception = ReconciliationException.objects.get(payment=payment)
        assert exception.exception_type == ExceptionType.STATUS_MISMATCH

    def test_matching_payment_is_counted_matched_no_exception(
        self, make_tenant, make_bill_with_control_number, mock_provider, make_user
    ):
        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant, amount=Decimal("1000"))
        initiate_payment(tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("1000"))

        run = run_reconciliation(tenant=tenant, actor=make_user())

        assert run.matched_count == 1
        assert run.exception_count == 0


@pytest.mark.django_db
class TestResolveException:
    def test_resolving_an_exception_marks_it_resolved(
        self, make_tenant, make_customer, make_customer_account, mock_provider, make_user
    ):
        from apps.billing.models import BillStatus
        from apps.billing.services import get_or_create_bill
        from apps.control_numbers.services import get_or_create_for_bill
        from apps.payments.models import Payment

        tenant = make_tenant()
        account = make_customer_account(tenant, make_customer(tenant))
        bill, _ = get_or_create_bill(
            tenant=tenant, customer_account=account, items=[{"description": "Fee", "unit_amount": Decimal("100")}]
        )
        bill.transition_to(BillStatus.ACTIVE)
        control_number, _ = get_or_create_for_bill(tenant=tenant, bill=bill)
        # A payment stuck UNKNOWN with no corresponding provider record —
        # querying it during reconciliation will not resolve it, so an
        # exception is guaranteed to be opened (see the reconciliation
        # service tests for the same technique).
        Payment.objects.create(
            tenant=tenant, control_number=control_number, provider=mock_provider,
            amount=Decimal("100"), currency="TZS", status=PaymentStatus.UNKNOWN,
            merchant_reference="STUCK-FOR-RESOLVE-TEST",
        )

        user = make_user()
        run = run_reconciliation(tenant=tenant, actor=user)
        exception = run.exceptions.first()
        assert exception is not None
        assert exception.status == ExceptionStatus.OPEN

        resolve_exception(exception, actor=user, notes="Confirmed with provider support.")

        exception.refresh_from_db()
        assert exception.status == ExceptionStatus.RESOLVED
        assert exception.resolved_by == user
        assert exception.resolution_notes == "Confirmed with provider support."
