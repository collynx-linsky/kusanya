from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.audit.services import record_audit_event
from apps.tenants.forms import TenantOnboardingForm
from apps.tenants.models import Tenant, TenantMembership, TenantRole
from apps.tenants.permissions import require_platform_role
from apps.users.models import PlatformRole

User = get_user_model()


def onboard(request):
    """Journey A: institution registration → tenant (PENDING) + admin user."""
    if request.method == "POST":
        form = TenantOnboardingForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            with transaction.atomic():
                user = User.objects.create_user(
                    email=data["admin_email"],
                    password=data["admin_password"],
                    first_name=data["admin_first_name"],
                    last_name=data["admin_last_name"],
                )
                tenant = Tenant.objects.create(
                    name=data["institution_name"],
                    sector=data["sector"],
                    contact_email=data["contact_email"],
                    contact_phone=data["contact_phone"],
                    status=Tenant.Status.PENDING,
                )
                TenantMembership.objects.create(
                    tenant=tenant, user=user, role=TenantRole.ADMIN
                )
                record_audit_event(
                    actor=user,
                    tenant=tenant,
                    action="tenant.registered",
                    target=tenant,
                    metadata={"sector": tenant.sector},
                )
            messages.success(
                request,
                "Registration received. Your institution is pending platform "
                "approval before you can start billing.",
            )
            login(request, user)
            return redirect("core:dashboard-router")
    else:
        form = TenantOnboardingForm()

    return render(request, "tenants/onboarding.html", {"form": form})


@login_required
def dashboard(request):
    """Tenant portal shell. Real collections/billing figures arrive in later
    phases — this shows only what genuinely exists today (membership,
    tenant status) rather than fabricating numbers for empty domains."""
    tenant = request.tenant
    if tenant is None:
        return render(request, "dashboard/no_access.html")

    context = {
        "tenant": tenant,
        "member_count": TenantMembership.objects.filter(tenant=tenant, is_active=True).count(),
    }
    return render(request, "dashboard/tenant_dashboard.html", context)


@login_required
@require_platform_role(PlatformRole.SUPER_ADMIN, PlatformRole.OPERATIONS_ADMIN)
def pending_tenants(request):
    tenants = Tenant.objects.filter(status=Tenant.Status.PENDING).order_by("created_at")
    return render(request, "tenants/pending_list.html", {"tenants": tenants})


@login_required
@require_platform_role(PlatformRole.SUPER_ADMIN, PlatformRole.OPERATIONS_ADMIN)
def approve_tenant(request, pk):
    tenant = get_object_or_404(Tenant, pk=pk)
    if request.method == "POST":
        tenant.status = Tenant.Status.ACTIVE
        tenant.approved_at = timezone.now()
        tenant.approved_by = request.user
        tenant.save(update_fields=["status", "approved_at", "approved_by", "updated_at"])
        record_audit_event(
            actor=request.user,
            tenant=tenant,
            action="tenant.approved",
            target=tenant,
        )
        messages.success(request, f"{tenant.name} approved and activated.")
    return redirect("tenants:pending-tenants")
