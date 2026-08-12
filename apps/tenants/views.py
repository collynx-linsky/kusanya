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
    """Tenant portal shell — shows only what genuinely exists today
    (membership, customers, bills, control numbers, collections,
    platform fees, open reconciliation exceptions) rather than
    fabricating tiles for domains that don't exist yet."""
    tenant = request.tenant
    if tenant is None:
        return render(request, "dashboard/no_access.html")

    from django.db.models import Sum

    from apps.billing.models import Bill
    from apps.control_numbers.models import ControlNumber
    from apps.customers.models import Customer
    from apps.payments.models import Payment, PaymentStatus
    from apps.reconciliation.models import ExceptionStatus, ReconciliationException
    from apps.revenue.models import RevenueEvent

    gross_collected = (
        Payment.objects.filter(tenant=tenant, status=PaymentStatus.SUCCESSFUL).aggregate(total=Sum("amount"))[
            "total"
        ]
        or 0
    )
    platform_fees_paid = (
        RevenueEvent.objects.filter(tenant=tenant).aggregate(total=Sum("amount"))["total"] or 0
    )

    context = {
        "tenant": tenant,
        "member_count": TenantMembership.objects.filter(tenant=tenant, is_active=True).count(),
        "customer_count": Customer.objects.filter(tenant=tenant).count(),
        "bill_count": Bill.objects.filter(tenant=tenant).count(),
        "control_number_count": ControlNumber.objects.filter(tenant=tenant).count(),
        "gross_collected": gross_collected,
        "platform_fees_paid": platform_fees_paid,
        "open_exception_count": ReconciliationException.objects.filter(
            tenant=tenant, status=ExceptionStatus.OPEN
        ).count(),
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
