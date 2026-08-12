from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.api.credential_services import create_credential, revoke_credential, rotate_credential
from apps.api.forms import ApiCredentialForm
from apps.api.models import ApiCredential
from apps.tenants.models import TenantRole
from apps.tenants.permissions import require_tenant_role

_CAN_MANAGE = (TenantRole.ADMIN,)


@login_required
@require_tenant_role(*_CAN_MANAGE)
def credential_list(request):
    credentials = ApiCredential.objects.filter(tenant=request.tenant)
    return render(request, "api/credential_list.html", {"credentials": credentials})


@login_required
@require_tenant_role(*_CAN_MANAGE)
def credential_create(request):
    if request.method == "POST":
        form = ApiCredentialForm(request.POST)
        if form.is_valid():
            credential, raw_secret = create_credential(
                tenant=request.tenant, name=form.cleaned_data["name"], actor=request.user
            )
            return render(
                request, "api/credential_secret_shown.html",
                {"credential": credential, "raw_secret": raw_secret, "action": "created"},
            )
    else:
        form = ApiCredentialForm()
    return render(request, "api/credential_form.html", {"form": form})


@login_required
@require_tenant_role(*_CAN_MANAGE)
def credential_rotate(request, pk):
    credential = get_object_or_404(ApiCredential, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        raw_secret = rotate_credential(credential, actor=request.user)
        return render(
            request, "api/credential_secret_shown.html",
            {"credential": credential, "raw_secret": raw_secret, "action": "rotated"},
        )
    return redirect("api_credentials:list")


@login_required
@require_tenant_role(*_CAN_MANAGE)
def credential_revoke(request, pk):
    credential = get_object_or_404(ApiCredential, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        revoke_credential(credential, actor=request.user)
        messages.success(request, f"Credential '{credential.name}' revoked.")
    return redirect("api_credentials:list")
