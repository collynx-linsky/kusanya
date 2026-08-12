from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.tenants.models import TenantRole
from apps.tenants.permissions import require_tenant_role
from apps.webhooks.forms import WebhookEndpointForm
from apps.webhooks.models import WebhookDelivery, WebhookEndpoint

_CAN_MANAGE = (TenantRole.ADMIN, TenantRole.FINANCE_MANAGER)


@login_required
@require_tenant_role(*_CAN_MANAGE)
def endpoint_list(request):
    endpoints = WebhookEndpoint.objects.filter(tenant=request.tenant)
    return render(request, "webhooks/list.html", {"endpoints": endpoints})


@login_required
@require_tenant_role(*_CAN_MANAGE)
def endpoint_create(request):
    if request.method == "POST":
        form = WebhookEndpointForm(request.POST)
        if form.is_valid():
            endpoint = form.save(commit=False)
            endpoint.tenant = request.tenant
            endpoint.save()
            messages.success(
                request,
                f"Webhook endpoint created. Signing secret: {endpoint.secret} "
                "— shown once here; store it securely, it's needed to verify deliveries.",
            )
            return redirect("webhooks:list")
    else:
        form = WebhookEndpointForm()
    return render(request, "webhooks/form.html", {"form": form})


@login_required
@require_tenant_role(*_CAN_MANAGE)
def endpoint_deliveries(request, pk):
    endpoint = get_object_or_404(WebhookEndpoint, pk=pk, tenant=request.tenant)
    deliveries = WebhookDelivery.objects.filter(endpoint=endpoint)[:100]
    return render(request, "webhooks/deliveries.html", {"endpoint": endpoint, "deliveries": deliveries})
