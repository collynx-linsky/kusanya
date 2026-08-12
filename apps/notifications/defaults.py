"""
Default notification copy. build spec section 19: "Do not hard-code
notification text into payment logic. Use templates." — this is the one
place that requirement lives for templates a tenant hasn't customized.
Payment/billing/control-number code never constructs notification text
itself; it only calls apps.notifications.services.send_notification()
with an event type and a context dict.

Every template uses only the variable vocabulary build spec section 19
specifies: {institution_name} {customer_name} {bill_number}
{control_number} {paid_amount} {remaining_balance} {payment_reference}
{receipt_number}. A given event only fills in the variables that make
sense for it — see apps.notifications.services._render for how missing
variables are handled (blank, never a KeyError).
"""

from apps.notifications.models import NotificationChannel, NotificationEventType

# {event_type: {channel: {"subject": ..., "body": ...}}}
# `subject` is ignored for SMS (no subject line).
DEFAULT_TEMPLATES = {
    NotificationEventType.BILL_CREATED: {
        NotificationChannel.EMAIL: {
            "subject": "New bill from {institution_name}",
            "body": (
                "Dear {customer_name},\n\n"
                "{institution_name} has issued bill {bill_number}.\n\n"
                "Regards,\n{institution_name}"
            ),
        },
        NotificationChannel.SMS: {
            "body": "{institution_name}: new bill {bill_number} issued.",
        },
    },
    NotificationEventType.CONTROL_NUMBER_GENERATED: {
        NotificationChannel.EMAIL: {
            "subject": "Your control number from {institution_name}",
            "body": (
                "Dear {customer_name},\n\n"
                "Use control number {control_number} to pay bill {bill_number} "
                "at {institution_name}.\n\n"
                "Regards,\n{institution_name}"
            ),
        },
        NotificationChannel.SMS: {
            "body": "{institution_name}: pay using control number {control_number}.",
        },
    },
    NotificationEventType.PAYMENT_PENDING: {
        NotificationChannel.EMAIL: {
            "subject": "Payment pending — {institution_name}",
            "body": (
                "Dear {customer_name},\n\n"
                "Your payment (ref {payment_reference}) against control number "
                "{control_number} is pending confirmation.\n\n"
                "Regards,\n{institution_name}"
            ),
        },
        NotificationChannel.SMS: {
            "body": "{institution_name}: payment {payment_reference} pending.",
        },
    },
    NotificationEventType.PAYMENT_SUCCESSFUL: {
        NotificationChannel.EMAIL: {
            "subject": "Payment received — {institution_name}",
            "body": (
                "Dear {customer_name},\n\n"
                "We have received your payment of {paid_amount} (ref "
                "{payment_reference}) against control number {control_number}.\n"
                "Remaining balance: {remaining_balance}.\n"
                "Receipt: {receipt_number}.\n\n"
                "Regards,\n{institution_name}"
            ),
        },
        NotificationChannel.SMS: {
            "body": (
                "{institution_name}: payment of {paid_amount} received. "
                "Balance {remaining_balance}. Receipt {receipt_number}."
            ),
        },
    },
    NotificationEventType.PAYMENT_PARTIAL: {
        NotificationChannel.EMAIL: {
            "subject": "Partial payment received — {institution_name}",
            "body": (
                "Dear {customer_name},\n\n"
                "We have received a partial payment of {paid_amount} against "
                "bill {bill_number}. Remaining balance: {remaining_balance}.\n\n"
                "Regards,\n{institution_name}"
            ),
        },
        NotificationChannel.SMS: {
            "body": "{institution_name}: partial payment {paid_amount} received. Balance {remaining_balance}.",
        },
    },
    NotificationEventType.BILL_FULLY_PAID: {
        NotificationChannel.EMAIL: {
            "subject": "Bill fully paid — {institution_name}",
            "body": (
                "Dear {customer_name},\n\n"
                "Bill {bill_number} is now fully paid. Thank you.\n\n"
                "Regards,\n{institution_name}"
            ),
        },
        NotificationChannel.SMS: {
            "body": "{institution_name}: bill {bill_number} fully paid. Thank you.",
        },
    },
    NotificationEventType.PAYMENT_FAILED: {
        NotificationChannel.EMAIL: {
            "subject": "Payment failed — {institution_name}",
            "body": (
                "Dear {customer_name},\n\n"
                "Your payment (ref {payment_reference}) against control number "
                "{control_number} could not be completed. Please try again.\n\n"
                "Regards,\n{institution_name}"
            ),
        },
        NotificationChannel.SMS: {
            "body": "{institution_name}: payment {payment_reference} failed. Please try again.",
        },
    },
    NotificationEventType.PAYMENT_REVERSED: {
        NotificationChannel.EMAIL: {
            "subject": "Payment reversed — {institution_name}",
            "body": (
                "Dear {customer_name},\n\n"
                "Your payment (ref {payment_reference}) has been reversed.\n\n"
                "Regards,\n{institution_name}"
            ),
        },
        NotificationChannel.SMS: {
            "body": "{institution_name}: payment {payment_reference} reversed.",
        },
    },
    NotificationEventType.PAYMENT_REFUNDED: {
        NotificationChannel.EMAIL: {
            "subject": "Payment refunded — {institution_name}",
            "body": (
                "Dear {customer_name},\n\n"
                "Your payment (ref {payment_reference}) of {paid_amount} has "
                "been refunded.\n\n"
                "Regards,\n{institution_name}"
            ),
        },
        NotificationChannel.SMS: {
            "body": "{institution_name}: payment {payment_reference} refunded.",
        },
    },
    NotificationEventType.BALANCE_REMINDER: {
        NotificationChannel.EMAIL: {
            "subject": "Balance reminder — {institution_name}",
            "body": (
                "Dear {customer_name},\n\n"
                "This is a reminder that bill {bill_number} has an outstanding "
                "balance of {remaining_balance}.\n\n"
                "Regards,\n{institution_name}"
            ),
        },
        NotificationChannel.SMS: {
            "body": "{institution_name}: bill {bill_number} balance {remaining_balance} due.",
        },
    },
}
