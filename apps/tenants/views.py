from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.audit.services import record_audit_event
from apps.tenants.forms import TeamMemberForm, TenantOnboardingForm
from apps.tenants.models import Tenant, TenantMembership, TenantRole
from apps.tenants.permissions import require_platform_role, require_tenant_role
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
        # Real, most-recent-first activity — not a fabricated feed. See
        # docs/DESIGN_SYSTEM.md's "Dashboard" section.
        "recent_payments": Payment.objects.filter(tenant=tenant)
        .select_related("control_number")
        .order_by("-initiated_at")[:5],
    }
    return render(request, "dashboard/tenant_dashboard.html", context)


@login_required
@require_tenant_role(TenantRole.ADMIN)
def team_members(request):
    """The "Team members" stat card on the dashboard has always linked
    here in spirit -- TenantMembership.invited_by was built for this
    from the start (see the model's docstring), it just never had a UI
    until now. Tenant-admin-only: adding people who can act on your
    institution's money is exactly the kind of action that shouldn't be
    available to, say, a Viewer."""
    tenant = request.tenant
    memberships = (
        TenantMembership.objects.filter(tenant=tenant)
        .select_related("user", "invited_by")
        .order_by("-is_active", "user__email")
    )
    return render(request, "tenants/team_list.html", {"memberships": memberships})


@login_required
@require_tenant_role(TenantRole.ADMIN)
def team_member_create(request):
    tenant = request.tenant
    if request.method == "POST":
        form = TeamMemberForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            with transaction.atomic():
                user = User.objects.create_user(
                    email=data["email"],
                    password=data["password"],
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                )
                membership = TenantMembership.objects.create(
                    tenant=tenant, user=user, role=data["role"], invited_by=request.user,
                )
                record_audit_event(
                    actor=request.user,
                    tenant=tenant,
                    action="team_member.added",
                    target=membership,
                    metadata={"role": data["role"], "member_email": user.email},
                )
            messages.success(
                request,
                f"{user.email} added as {membership.get_role_display()}. Share the "
                f"sign-in email and password you set with them directly.",
            )
            return redirect("tenants:team")
    else:
        form = TeamMemberForm()

    return render(request, "tenants/team_member_form.html", {"form": form})


@login_required
@require_tenant_role(TenantRole.ADMIN)
def team_member_deactivate(request, pk):
    membership = get_object_or_404(TenantMembership, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        if membership.user_id == request.user.id:
            messages.error(request, "You can't deactivate your own membership.")
            return redirect("tenants:team")
        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])
        record_audit_event(
            actor=request.user, tenant=request.tenant, action="team_member.deactivated", target=membership,
        )
        messages.success(request, f"{membership.user.email} removed from the team.")
    return redirect("tenants:team")


@login_required
@require_tenant_role(TenantRole.ADMIN)
def team_member_activate(request, pk):
    membership = get_object_or_404(TenantMembership, pk=pk, tenant=request.tenant)
    if request.method == "POST":
        membership.is_active = True
        membership.save(update_fields=["is_active", "updated_at"])
        record_audit_event(
            actor=request.user, tenant=request.tenant, action="team_member.reactivated", target=membership,
        )
        messages.success(request, f"{membership.user.email} reactivated.")
    return redirect("tenants:team")


@login_required
@require_platform_role(PlatformRole.SUPER_ADMIN, PlatformRole.OPERATIONS_ADMIN)
def pending_tenants(request):
    tenants = Tenant.objects.filter(status=Tenant.Status.PENDING).order_by("created_at")
    return render(request, "tenants/pending_list.html", {"tenants": tenants})


@login_required
@require_platform_role(PlatformRole.SUPER_ADMIN, PlatformRole.OPERATIONS_ADMIN)
def platform_create_tenant(request):
    """Journey B: a platform administrator registers an institution
    directly (e.g. onboarding a customer over the phone, or a pilot
    partner that shouldn't sit in the public queue) — the in-app
    alternative to reaching for Django admin. Reuses the exact same
    form and creation logic as the public self-service path
    (`onboard`, above), with two differences: the tenant is created
    already ACTIVE rather than PENDING (a platform admin creating it
    themselves *is* the approval), and the audit trail records who did
    it (`tenant.created_by_platform`, distinct from the self-service
    `tenant.registered` event) so "who let this tenant in" always has a
    real, honest answer either way.
    """
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
                    status=Tenant.Status.ACTIVE,
                    approved_at=timezone.now(),
                    approved_by=request.user,
                )
                TenantMembership.objects.create(
                    tenant=tenant, user=user, role=TenantRole.ADMIN
                )
                record_audit_event(
                    actor=request.user,
                    tenant=tenant,
                    action="tenant.created_by_platform",
                    target=tenant,
                    metadata={"sector": tenant.sector, "admin_email": user.email},
                )
            messages.success(
                request,
                f"{tenant.name} created and activated. Share the sign-in email "
                f"and password you set with {user.email} directly.",
            )
            return redirect("tenants:pending-tenants")
    else:
        form = TenantOnboardingForm()

    return render(request, "tenants/platform_create.html", {"form": form})


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
