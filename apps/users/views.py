from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import redirect, render

from apps.audit.services import record_audit_event
from apps.tenants.models import TenantMembership
from apps.tenants.permissions import require_platform_role
from apps.users.forms import ACCESS_PLATFORM_STAFF, ACCESS_TENANT_MEMBER, PlatformUserCreateForm
from apps.users.models import PlatformMembership, PlatformRole

User = get_user_model()


@login_required
@require_platform_role(PlatformRole.SUPER_ADMIN, PlatformRole.OPERATIONS_ADMIN)
def platform_users(request):
    """Every user account on the platform, in one place -- the real
    in-app answer to "who can sign in and what can they do," instead
    of that only being answerable from Django admin across three
    separate tables (User, TenantMembership, PlatformMembership)."""
    users = (
        User.objects.all()
        .prefetch_related("tenant_memberships__tenant", "platform_memberships")
        .order_by("email")
    )
    paginator = Paginator(users, 50)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "users/platform_list.html", {"page_obj": page_obj})


@login_required
@require_platform_role(PlatformRole.SUPER_ADMIN, PlatformRole.OPERATIONS_ADMIN)
def platform_user_create(request):
    if request.method == "POST":
        form = PlatformUserCreateForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            with transaction.atomic():
                user = User.objects.create_user(
                    email=data["email"],
                    password=data["password"],
                    first_name=data["first_name"],
                    last_name=data["last_name"],
                )
                if data["access_type"] == ACCESS_TENANT_MEMBER:
                    tenant = data["tenant"]
                    membership = TenantMembership.objects.create(
                        tenant=tenant, user=user, role=data["tenant_role"], invited_by=request.user,
                    )
                    record_audit_event(
                        actor=request.user,
                        tenant=tenant,
                        action="user.created_by_platform",
                        target=membership,
                        metadata={"role": data["tenant_role"], "user_email": user.email},
                    )
                    messages.success(request, f"{user.email} created and added to {tenant.name}.")
                else:
                    # is_staff=True, not just a PlatformMembership row --
                    # the sidebar's "Platform admin" section (and
                    # everything under it) is gated on user.is_staff, so
                    # a platform role with is_staff=False would grant
                    # access require_platform_role checks for but leave
                    # no way to reach it through the UI. See
                    # ARCHITECTURE_DECISIONS ADR-043.
                    user.is_staff = True
                    user.save(update_fields=["is_staff"])
                    PlatformMembership.objects.create(user=user, role=data["platform_role"])
                    record_audit_event(
                        actor=request.user,
                        action="user.created_by_platform",
                        target=user,
                        metadata={"platform_role": data["platform_role"], "user_email": user.email},
                    )
                    messages.success(request, f"{user.email} created as platform staff.")
            return redirect("users:platform-list")
    else:
        form = PlatformUserCreateForm()

    return render(request, "users/platform_create.html", {"form": form})
