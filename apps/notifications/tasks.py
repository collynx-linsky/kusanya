"""
Async notification delivery — never sent inline in a payment/billing
request (build spec section 19: "use background workers for sending").
"""

import logging

from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone

from apps.notifications.models import Notification, NotificationChannel, NotificationStatus

logger = logging.getLogger("kusanya")


def _deliver_email(notification: Notification) -> None:
    send_mail(
        subject=notification.subject,
        message=notification.body,
        from_email=None,  # uses settings.DEFAULT_FROM_EMAIL
        recipient_list=[notification.recipient],
        fail_silently=False,
    )


def _deliver_mock_sms(notification: Notification) -> None:
    """MOCK/SANDBOX SMS channel. No real SMS gateway is integrated — build
    spec section 43's "no invented provider APIs" applies just as much to
    SMS/WhatsApp gateways as to payment providers. This logs the message
    that *would* be sent, clearly labeled, rather than pretending
    delivery occurred silently."""
    logger.info("[MOCK SMS] to=%s body=%s", notification.recipient, notification.body)


_DELIVERY_HANDLERS = {
    NotificationChannel.EMAIL: _deliver_email,
    NotificationChannel.SMS: _deliver_mock_sms,
}


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def deliver_notification(self, notification_id: str):
    try:
        notification = Notification.objects.select_related("tenant").get(id=notification_id)
    except Notification.DoesNotExist:
        logger.warning("deliver_notification: Notification %s no longer exists", notification_id)
        return

    if notification.status == NotificationStatus.SENT:
        return  # already delivered (defensive)

    handler = _DELIVERY_HANDLERS.get(notification.channel)
    if handler is None:
        # WhatsApp/push are architecture-ready (channel + template
        # support exist) but have no delivery handler — see
        # docs/NOTIFICATION_SPEC.md. Fail loudly rather than silently
        # dropping the message.
        notification.status = NotificationStatus.FAILED
        notification.error_message = f"No delivery handler implemented for channel '{notification.channel}'."
        notification.save(update_fields=["status", "error_message", "updated_at"])
        return

    try:
        handler(notification)
    except Exception as exc:
        notification.status = NotificationStatus.FAILED
        notification.error_message = str(exc)[:500]
        notification.save(update_fields=["status", "error_message", "updated_at"])
        raise self.retry(exc=exc)

    notification.status = NotificationStatus.SENT
    notification.sent_at = timezone.now()
    notification.save(update_fields=["status", "sent_at", "updated_at"])
