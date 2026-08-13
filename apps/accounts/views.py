from django.contrib import messages
from django.contrib.auth import get_user_model, login as auth_login
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache

from apps.accounts.forms import EmailAuthenticationForm
from apps.accounts.models import MFADevice
from apps.accounts.throttle import is_locked_out, record_failure, reset
from apps.audit.context import client_ip_from_request

User = get_user_model()


def _login_throttle_identifier(request) -> str:
    ip = client_ip_from_request(request) or "unknown"
    email = request.POST.get("username", "").strip().lower()
    return f"{ip}:{email}"


class EmailLoginView(LoginView):
    """Two changes from a stock Django LoginView:

    1. Brute-force lockout: MAX_ATTEMPTS failed submissions for the same
       (IP, email) pair within LOCKOUT_SECONDS are rejected outright,
       without even attempting authentication — see apps.accounts.throttle.
    2. MFA interception: if the authenticated user has a confirmed
       MFADevice, the session is NOT established here — the user is
       redirected to enter their code first. See mfa_verify() below.
    """

    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        identifier = _login_throttle_identifier(request)
        if is_locked_out("login", identifier):
            messages.error(request, "Too many failed sign-in attempts. Please try again in a few minutes.")
            form = self.get_form()
            return self.render_to_response(self.get_context_data(form=form))
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        reset("login", _login_throttle_identifier(self.request))

        user = form.get_user()
        device = MFADevice.objects.filter(user=user, confirmed=True).first()
        if device is not None:
            self.request.session["mfa_pending_user_id"] = str(user.pk)
            self.request.session["mfa_pending_backend"] = getattr(
                user, "backend", "django.contrib.auth.backends.ModelBackend"
            )
            return redirect("accounts:mfa-verify")

        return super().form_valid(form)

    def form_invalid(self, form):
        record_failure("login", _login_throttle_identifier(self.request))
        return super().form_invalid(form)


class KusanyaLogoutView(LogoutView):
    next_page = "accounts:login"


@never_cache
def mfa_verify(request):
    """The second step of login for a user with confirmed MFA. Not
    `@login_required` — the user isn't logged in yet; access is gated by
    `mfa_pending_user_id` in the session, set only by a just-succeeded
    password check in EmailLoginView.form_valid()."""
    from apps.accounts.mfa_services import consume_backup_code
    from apps.accounts.totp import verify_totp

    user_id = request.session.get("mfa_pending_user_id")
    if not user_id:
        return redirect("accounts:login")

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        del request.session["mfa_pending_user_id"]
        return redirect("accounts:login")

    if request.method == "POST":
        if is_locked_out("mfa", str(user.pk)):
            messages.error(request, "Too many failed codes. Please sign in again in a few minutes.")
            return render(request, "accounts/mfa_verify.html")

        code = request.POST.get("code", "").strip()
        device = MFADevice.objects.filter(user=user, confirmed=True).first()

        verified = device is not None and verify_totp(device.secret, code)
        if not verified:
            verified = consume_backup_code(user, code)

        if verified:
            reset("mfa", str(user.pk))
            backend = request.session.pop("mfa_pending_backend", "django.contrib.auth.backends.ModelBackend")
            del request.session["mfa_pending_user_id"]
            auth_login(request, user, backend=backend)
            if device is not None:
                from django.utils import timezone

                device.last_used_at = timezone.now()
                device.save(update_fields=["last_used_at", "updated_at"])
            return redirect(request.GET.get("next") or "core:dashboard-router")

        record_failure("mfa", str(user.pk))
        messages.error(request, "Invalid code.")

    return render(request, "accounts/mfa_verify.html")
