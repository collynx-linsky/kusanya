from decimal import Decimal

import pytest

from apps.notifications.models import Notification, NotificationChannel, NotificationEventType, NotificationTemplate
from apps.notifications.services import render_template, send_notification
from apps.notifications.tasks import deliver_notification
from apps.payments.services import initiate_payment


@pytest.mark.django_db
class TestTemplateRendering:
    def test_default_template_substitutes_variables(self, make_tenant):
        tenant = make_tenant()
        subject, body = render_template(
            tenant=tenant,
            event_type=NotificationEventType.BILL_CREATED,
            channel=NotificationChannel.EMAIL,
            context={"institution_name": "Acme School", "customer_name": "Amina", "bill_number": "BILL-1"},
        )
        assert "Acme School" in subject
        assert "Amina" in body
        assert "BILL-1" in body

    def test_missing_variable_renders_blank_not_keyerror(self, make_tenant):
        tenant = make_tenant()
        # BILL_CREATED's template never mentions {paid_amount}, but this
        # proves the rendering path tolerates a template that does.
        subject, body = render_template(
            tenant=tenant,
            event_type=NotificationEventType.PAYMENT_SUCCESSFUL,
            channel=NotificationChannel.SMS,
            context={"institution_name": "Acme"},  # customer_name, paid_amount etc. all omitted
        )
        assert body  # rendered without raising

    def test_tenant_override_takes_precedence_over_default(self, make_tenant):
        tenant = make_tenant()
        NotificationTemplate.objects.create(
            tenant=tenant,
            event_type=NotificationEventType.BILL_CREATED,
            channel=NotificationChannel.EMAIL,
            subject="Custom subject for {institution_name}",
            body="Custom body naming {customer_name}.",
        )
        subject, body = render_template(
            tenant=tenant, event_type=NotificationEventType.BILL_CREATED, channel=NotificationChannel.EMAIL,
            context={"institution_name": "Acme", "customer_name": "Amina"},
        )
        assert subject == "Custom subject for Acme"
        assert body == "Custom body naming Amina."

    def test_inactive_override_is_ignored(self, make_tenant):
        tenant = make_tenant()
        NotificationTemplate.objects.create(
            tenant=tenant, event_type=NotificationEventType.BILL_CREATED, channel=NotificationChannel.EMAIL,
            subject="Should not be used", body="Inactive", is_active=False,
        )
        subject, _body = render_template(
            tenant=tenant, event_type=NotificationEventType.BILL_CREATED, channel=NotificationChannel.EMAIL,
            context={"institution_name": "Acme"},
        )
        assert subject != "Should not be used"


@pytest.mark.django_db
class TestSendNotification:
    def test_creates_one_notification_per_channel_with_a_recipient(self, make_tenant):
        tenant = make_tenant()
        notifications = send_notification(
            tenant=tenant, event_type=NotificationEventType.BILL_CREATED,
            context={"institution_name": "Acme", "customer_name": "Amina", "bill_number": "B1"},
            recipient_email="amina@example.com", recipient_phone="+255700000000",
        )
        assert len(notifications) == 2
        channels = {n.channel for n in notifications}
        assert channels == {NotificationChannel.EMAIL, NotificationChannel.SMS}

    def test_skips_channel_with_no_recipient(self, make_tenant):
        tenant = make_tenant()
        notifications = send_notification(
            tenant=tenant, event_type=NotificationEventType.BILL_CREATED,
            context={"institution_name": "Acme", "customer_name": "Amina", "bill_number": "B1"},
            recipient_email="amina@example.com", recipient_phone="",
        )
        assert len(notifications) == 1
        assert notifications[0].channel == NotificationChannel.EMAIL


@pytest.mark.django_db
class TestDelivery:
    def test_email_delivery_lands_in_outbox(self, make_tenant, mailoutbox):
        tenant = make_tenant()
        notification = Notification.objects.create(
            tenant=tenant, event_type=NotificationEventType.BILL_CREATED, channel=NotificationChannel.EMAIL,
            recipient="amina@example.com", subject="Hello", body="Body text",
        )
        deliver_notification.run(str(notification.id))

        notification.refresh_from_db()
        assert notification.status == "sent"
        assert notification.sent_at is not None
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == ["amina@example.com"]
        assert mailoutbox[0].subject == "Hello"

    def test_mock_sms_delivery_marks_sent_without_a_real_gateway(self, make_tenant):
        tenant = make_tenant()
        notification = Notification.objects.create(
            tenant=tenant, event_type=NotificationEventType.BILL_CREATED, channel=NotificationChannel.SMS,
            recipient="+255700000000", subject="", body="SMS body",
        )
        deliver_notification.run(str(notification.id))

        notification.refresh_from_db()
        assert notification.status == "sent"

    def test_unimplemented_channel_fails_loudly_not_silently(self, make_tenant):
        tenant = make_tenant()
        notification = Notification.objects.create(
            tenant=tenant, event_type=NotificationEventType.BILL_CREATED, channel=NotificationChannel.WHATSAPP,
            recipient="+255700000000", subject="", body="body",
        )
        deliver_notification.run(str(notification.id))

        notification.refresh_from_db()
        assert notification.status == "failed"
        assert notification.error_message


@pytest.mark.django_db
class TestIntegrationWithPaymentEvents:
    def test_bill_and_control_number_creation_send_notifications(
        self, make_tenant, make_customer, make_customer_account
    ):
        from apps.billing.models import BillStatus
        from apps.billing.services import get_or_create_bill
        from apps.control_numbers.services import get_or_create_for_bill

        tenant = make_tenant()
        customer = make_customer(tenant, email="amina@example.com")
        account = make_customer_account(tenant, customer)
        bill, _ = get_or_create_bill(
            tenant=tenant, customer_account=account, items=[{"description": "Fee", "unit_amount": Decimal("1000")}]
        )
        bill.transition_to(BillStatus.ACTIVE)
        get_or_create_for_bill(tenant=tenant, bill=bill)

        assert Notification.objects.filter(
            tenant=tenant, event_type=NotificationEventType.BILL_CREATED
        ).exists()
        assert Notification.objects.filter(
            tenant=tenant, event_type=NotificationEventType.CONTROL_NUMBER_GENERATED
        ).exists()

    def test_control_number_reuse_does_not_send_a_second_notification(
        self, make_tenant, make_bill_with_control_number
    ):
        from apps.control_numbers.services import get_or_create_for_bill

        tenant = make_tenant()
        bill, control_number = make_bill_with_control_number(tenant)
        before = Notification.objects.filter(
            tenant=tenant, event_type=NotificationEventType.CONTROL_NUMBER_GENERATED
        ).count()

        get_or_create_for_bill(tenant=tenant, bill=bill)  # reuse

        after = Notification.objects.filter(
            tenant=tenant, event_type=NotificationEventType.CONTROL_NUMBER_GENERATED
        ).count()
        assert after == before

    def test_full_bill_payment_sends_bill_fully_paid_not_generic_successful(
        self, make_tenant, make_customer, make_customer_account, mock_provider
    ):
        from apps.billing.models import BillStatus
        from apps.billing.services import get_or_create_bill
        from apps.control_numbers.services import get_or_create_for_bill

        tenant = make_tenant()
        customer = make_customer(tenant, email="amina@example.com")
        account = make_customer_account(tenant, customer)
        bill, _ = get_or_create_bill(
            tenant=tenant, customer_account=account, items=[{"description": "Fee", "unit_amount": Decimal("1000")}]
        )
        bill.transition_to(BillStatus.ACTIVE)
        control_number, _ = get_or_create_for_bill(tenant=tenant, bill=bill)

        initiate_payment(tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("1000"))

        assert Notification.objects.filter(
            tenant=tenant, event_type=NotificationEventType.BILL_FULLY_PAID
        ).exists()
        assert not Notification.objects.filter(
            tenant=tenant, event_type=NotificationEventType.PAYMENT_SUCCESSFUL
        ).exists()

    def test_partial_payment_sends_payment_partial(
        self, make_tenant, make_customer, make_customer_account, mock_provider
    ):
        from apps.billing.models import BillStatus
        from apps.billing.services import get_or_create_bill
        from apps.control_numbers.services import get_or_create_for_bill

        tenant = make_tenant()
        customer = make_customer(tenant, email="amina@example.com")
        account = make_customer_account(tenant, customer)
        bill, _ = get_or_create_bill(
            tenant=tenant, customer_account=account, items=[{"description": "Fee", "unit_amount": Decimal("1000")}]
        )
        bill.transition_to(BillStatus.ACTIVE)
        control_number, _ = get_or_create_for_bill(tenant=tenant, bill=bill)

        initiate_payment(tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("400"))

        assert Notification.objects.filter(
            tenant=tenant, event_type=NotificationEventType.PAYMENT_PARTIAL
        ).exists()
