"""Self-service MFA management for an already-logged-in user — distinct
from apps.accounts.views, which handles the pre-login auth flow."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.accounts.mfa_services import confirm_device, disable_mfa, generate_backup_codes
from apps.accounts.models import MFADevice
from apps.accounts.totp import build_otpauth_qr_svg, build_otpauth_uri


@login_required
def mfa_status(request):
    device = MFADevice.objects.filter(user=request.user, confirmed=True).first()
    backup_codes_remaining = request.user.backup_codes.filter(used_at__isnull=True).count() if device else 0
    return render(
        request, "accounts/mfa_status.html",
        {"device": device, "backup_codes_remaining": backup_codes_remaining},
    )


@login_required
def mfa_setup(request):
    existing = MFADevice.objects.filter(user=request.user, confirmed=True).first()
    if existing is not None:
        messages.info(request, "MFA is already enabled on your account.")
        return redirect("accounts:mfa-status")

    device, _created = MFADevice.objects.get_or_create(user=request.user)

    if request.method == "POST":
        code = request.POST.get("code", "").strip()
        if confirm_device(device, code, actor=request.user):
            backup_codes = generate_backup_codes(request.user, actor=request.user)
            return render(request, "accounts/mfa_backup_codes.html", {"codes": backup_codes})
        messages.error(request, "That code didn't verify — check your authenticator app and try again.")

    otpauth_uri = build_otpauth_uri(secret_b32=device.secret, account_name=request.user.email)
    qr_svg = build_otpauth_qr_svg(otpauth_uri)
    return render(
        request, "accounts/mfa_setup.html",
        {"device": device, "otpauth_uri": otpauth_uri, "qr_svg": qr_svg},
    )


@login_required
def mfa_disable(request):
    if request.method == "POST":
        disable_mfa(request.user, actor=request.user)
        messages.success(request, "MFA has been disabled on your account.")
    return redirect("accounts:mfa-status")


@login_required
def mfa_regenerate_backup_codes(request):
    device = MFADevice.objects.filter(user=request.user, confirmed=True).first()
    if device is None:
        return redirect("accounts:mfa-status")
    if request.method == "POST":
        codes = generate_backup_codes(request.user, actor=request.user)
        return render(request, "accounts/mfa_backup_codes.html", {"codes": codes})
    return redirect("accounts:mfa-status")
