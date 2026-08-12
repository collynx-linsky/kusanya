"""
Entry point domain code uses to notify a customer — never construct
notification text inline in billing/payment code (build spec section 19).
Callers pass an event type and a context dict; template resolution
(tenant override, falling back to apps.notifications.defaults) and
channel selection happen here.
"""

from django.db import transaction

from apps.core.correlation import get_correlation_id
from apps.notifications.defaults import DEFAULT_TEMPLATES
from apps.notifications.models import Notification, NotificationChannel, NotificationTemplate


class _SafeDict(dict):
    """Missing template variables render as empty string, never KeyError
    — different events have different available variables (a BILL_CREATED
    notification has no {paid_amount}, for instance) and a template
    referencing one that isn't available for that event shouldn't crash
    delivery."""

    def __missing__(self, key):
        return ""


def render_template(*, tenant, event_type: str, channel: str, context: dict) -> tuple[str, str]:
    override = NotificationTemplate.objects.filter(
        tenant=tenant, event_type=event_type, channel=channel, is_active=True
    ).first()

    if override is not None:
        subject_tpl, body_tpl = override.subject, override.body
    else:
        defaults = DEFAULT_TEMPLATES.get(event_type, {}).get(channel)
        if defaults is None:
            raise KeyError(f"No template (default or tenant override) for {event_type}/{channel}")
        subject_tpl, body_tpl = defaults.get("subject", ""), defaults["body"]

    safe_context = _SafeDict(context)
    return subject_tpl.format_map(safe_context), body_tpl.format_map(safe_context)


def send_notification(
    *,
    tenant,
    event_type: str,
    context: dict,
    recipient_email: str = "",
    recipient_phone: str = "",
) -> list[Notification]:
    """Creates one Notification per channel with a usable recipient
    address, and enqueues delivery for each. Silently sends nothing for a
    channel with no recipient (e.g. a customer with no phone number just
    doesn't get an SMS) rather than erroring."""
    notifications = []
    correlation_id = get_correlation_id()

    if recipient_email:
        subject, body = render_template(
            tenant=tenant, event_type=event_type, channel=NotificationChannel.EMAIL, context=context
        )
        notification = Notification.objects.create(
            tenant=tenant, event_type=event_type, channel=NotificationChannel.EMAIL,
            recipient=recipient_email, subject=subject, body=body, correlation_id=correlation_id,
        )
        notifications.append(notification)
        _enqueue(notification.id)

    if recipient_phone:
        _subject, body = render_template(
            tenant=tenant, event_type=event_type, channel=NotificationChannel.SMS, context=context
        )
        notification = Notification.objects.create(
            tenant=tenant, event_type=event_type, channel=NotificationChannel.SMS,
            recipient=recipient_phone, subject="", body=body, correlation_id=correlation_id,
        )
        notifications.append(notification)
        _enqueue(notification.id)

    return notifications


def _enqueue(notification_id) -> None:
    def _send():
        from apps.notifications.tasks import deliver_notification

        deliver_notification.delay(str(notification_id))

    transaction.on_commit(_send)
