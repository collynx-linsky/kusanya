"""Wires Django's built-in auth signals to the audit log, per build spec
section 29 (login / logout / failed login must be audited)."""

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from apps.audit.services import record_audit_event


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    record_audit_event(action="auth.login", actor=user)


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    record_audit_event(action="auth.logout", actor=user)


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    record_audit_event(
        action="auth.login_failed",
        metadata={"attempted_email": credentials.get("email", credentials.get("username", ""))},
    )
