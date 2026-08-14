"""
Tenant isolation and RBAC are the two invariants this platform cannot ship
without (build spec sections 7 and 8) — these tests exist to fail loudly
the moment either is violated.
"""

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.tenants.middleware import TenantResolutionMiddleware
from apps.tenants.models import Tenant, TenantRole
from apps.tenants.permissions import (
    get_tenant_role,
    has_platform_role,
    has_tenant_role,
    require_tenant_role,
)
from apps.users.models import PlatformRole


@pytest.mark.django_db
class TestTenantResolutionMiddleware:
    def test_session_tenant_is_honoured_when_membership_active(
        self, rf, make_user, make_tenant, make_membership
    ):
        user = make_user()
        tenant = make_tenant()
        make_membership(user, tenant)

        request = rf.get("/")
        request.user = user
        request.session = {"active_tenant_id": str(tenant.id)}

        TenantResolutionMiddleware(lambda r: r)(request)

        assert request.tenant == tenant

    def test_a_user_cannot_resolve_a_tenant_they_have_no_membership_in(
        self, rf, make_user, make_tenant
    ):
        """The core tenant-isolation guarantee: a session value alone is
        never sufficient — a stale/tampered active_tenant_id for a tenant
        the user isn't a member of must resolve to no tenant, not that
        tenant."""
        user = make_user()
        other_tenant = make_tenant(name="Someone Else's Institution")

        request = rf.get("/")
        request.user = user
        request.session = {"active_tenant_id": str(other_tenant.id)}

        TenantResolutionMiddleware(lambda r: r)(request)

        assert request.tenant is None
        assert "active_tenant_id" not in request.session

    def test_inactive_membership_does_not_resolve_tenant(
        self, rf, make_user, make_tenant, make_membership
    ):
        user = make_user()
        tenant = make_tenant()
        make_membership(user, tenant, is_active=False)

        request = rf.get("/")
        request.user = user
        request.session = {"active_tenant_id": str(tenant.id)}

        TenantResolutionMiddleware(lambda r: r)(request)

        assert request.tenant is None


@pytest.mark.django_db
class TestTenantIsolationAcrossPortal:
    def test_tenant_b_admin_cannot_see_tenant_a_dashboard_data(
        self, client, make_user, make_tenant, make_membership
    ):
        user_a = make_user(email="a@example.com")
        tenant_a = make_tenant(name="Tenant A")
        make_membership(user_a, tenant_a)

        user_b = make_user(email="b@example.com")
        tenant_b = make_tenant(name="Tenant B")
        make_membership(user_b, tenant_b)

        client.force_login(user_b)
        session = client.session
        # Attempt to impersonate tenant A via a forged session value.
        session["active_tenant_id"] = str(tenant_a.id)
        session.save()

        response = client.get(reverse("tenants:dashboard"))
        # Middleware must have dropped the forged tenant; dashboard view
        # falls back to the "no access" template rather than tenant A data.
        assert b"Tenant A" not in response.content


@pytest.mark.django_db
class TestRBACPermissions:
    def test_platform_role_grants_access(self, make_user, make_platform_role):
        user = make_user()
        make_platform_role(user, PlatformRole.FINANCE_ADMIN)
        assert has_platform_role(user, PlatformRole.FINANCE_ADMIN)
        assert not has_platform_role(user, PlatformRole.SUPER_ADMIN)

    def test_superuser_implicitly_has_every_platform_role(self, make_user):
        user = make_user(is_superuser=True)
        assert has_platform_role(user, PlatformRole.COMPLIANCE_ADMIN)

    def test_tenant_role_is_scoped_to_that_tenant_only(
        self, make_user, make_tenant, make_membership
    ):
        user = make_user()
        tenant_a = make_tenant(name="A")
        tenant_b = make_tenant(name="B")
        make_membership(user, tenant_a, role=TenantRole.FINANCE_MANAGER)

        assert has_tenant_role(user, tenant_a, TenantRole.FINANCE_MANAGER)
        assert not has_tenant_role(user, tenant_b, TenantRole.FINANCE_MANAGER)
        assert get_tenant_role(user, tenant_b) is None

    def test_require_tenant_role_decorator_denies_without_role(
        self, rf, make_user, make_tenant, make_membership
    ):
        user = make_user()
        tenant = make_tenant()
        make_membership(user, tenant, role=TenantRole.VIEWER)

        @require_tenant_role(TenantRole.FINANCE_MANAGER)
        def view(request):
            return "allowed"

        request = rf.get("/")
        request.user = user
        request.tenant = tenant

        with pytest.raises(PermissionDenied):
            view(request)

    def test_require_tenant_role_decorator_allows_with_role(
        self, rf, make_user, make_tenant, make_membership
    ):
        user = make_user()
        tenant = make_tenant()
        make_membership(user, tenant, role=TenantRole.FINANCE_MANAGER)

        @require_tenant_role(TenantRole.FINANCE_MANAGER)
        def view(request):
            return "allowed"

        request = rf.get("/")
        request.user = user
        request.tenant = tenant

        assert view(request) == "allowed"


@pytest.mark.django_db
class TestTenantOnboarding:
    def test_registration_creates_pending_tenant_and_admin_membership(self, client):
        response = client.post(
            reverse("tenants:onboard"),
            {
                "institution_name": "Kilimanjaro Clinic",
                "sector": "healthcare",
                "contact_email": "ops@kilimanjaroclinic.example",
                "contact_phone": "",
                "admin_first_name": "Amina",
                "admin_last_name": "Juma",
                "admin_email": "amina@kilimanjaroclinic.example",
                "admin_password": "SuperSecurePass123!",
            },
        )
        assert response.status_code == 302

        tenant = Tenant.objects.get(name="Kilimanjaro Clinic")
        assert tenant.status == Tenant.Status.PENDING
        assert tenant.memberships.filter(role=TenantRole.ADMIN).exists()

    def test_pending_tenant_cannot_be_approved_without_platform_role(
        self, client, make_user, make_tenant
    ):
        staff_without_role = make_user(email="staff@example.com", is_staff=True)
        tenant = make_tenant(status=Tenant.Status.PENDING)

        client.force_login(staff_without_role)
        response = client.post(reverse("tenants:approve-tenant", args=[tenant.id]))

        assert response.status_code == 403
        tenant.refresh_from_db()
        assert tenant.status == Tenant.Status.PENDING

    def test_platform_admin_can_approve_pending_tenant(
        self, client, make_user, make_tenant, make_platform_role
    ):
        admin = make_user(email="platform-admin@example.com", is_staff=True)
        make_platform_role(admin, PlatformRole.SUPER_ADMIN)
        tenant = make_tenant(status=Tenant.Status.PENDING)

        client.force_login(admin)
        response = client.post(reverse("tenants:approve-tenant", args=[tenant.id]))

        assert response.status_code == 302
        tenant.refresh_from_db()
        assert tenant.status == Tenant.Status.ACTIVE
        assert tenant.approved_by == admin

    def test_non_staff_cannot_reach_platform_create(self, client, make_user):
        non_staff = make_user(email="notstaff@example.com")
        client.force_login(non_staff)
        response = client.post(
            reverse("tenants:platform-create-tenant"),
            {
                "institution_name": "Should Not Exist",
                "sector": "healthcare",
                "contact_email": "ops@shouldnotexist.example",
                "contact_phone": "",
                "admin_first_name": "Nope",
                "admin_last_name": "Nope",
                "admin_email": "nope@shouldnotexist.example",
                "admin_password": "SuperSecurePass123!",
            },
        )
        assert response.status_code == 403
        assert not Tenant.objects.filter(name="Should Not Exist").exists()

    def test_platform_admin_can_create_an_already_active_tenant(
        self, client, make_user, make_platform_role
    ):
        from apps.audit.models import AuditLog

        admin = make_user(email="creator@example.com", is_staff=True)
        make_platform_role(admin, PlatformRole.SUPER_ADMIN)
        client.force_login(admin)

        response = client.post(
            reverse("tenants:platform-create-tenant"),
            {
                "institution_name": "Directly Created School",
                "sector": "education",
                "contact_email": "ops@directlycreated.example",
                "contact_phone": "",
                "admin_first_name": "Grace",
                "admin_last_name": "Mwangi",
                "admin_email": "grace@directlycreated.example",
                "admin_password": "SuperSecurePass123!",
            },
        )
        assert response.status_code == 302

        tenant = Tenant.objects.get(name="Directly Created School")
        assert tenant.status == Tenant.Status.ACTIVE
        assert tenant.approved_by == admin
        assert tenant.memberships.filter(role=TenantRole.ADMIN).exists()
        assert AuditLog.objects.filter(action="tenant.created_by_platform").exists()

    def test_platform_create_form_rejects_a_duplicate_institution_name(
        self, client, make_user, make_tenant, make_platform_role
    ):
        admin = make_user(email="creator2@example.com", is_staff=True)
        make_platform_role(admin, PlatformRole.SUPER_ADMIN)
        make_tenant(name="Already Exists Ltd")
        client.force_login(admin)

        response = client.post(
            reverse("tenants:platform-create-tenant"),
            {
                "institution_name": "Already Exists Ltd",
                "sector": "healthcare",
                "contact_email": "ops@dup.example",
                "contact_phone": "",
                "admin_first_name": "Dup",
                "admin_last_name": "Licate",
                "admin_email": "dup@dup.example",
                "admin_password": "SuperSecurePass123!",
            },
        )
        assert response.status_code == 200  # re-renders the form with the error
        assert "already registered" in response.content.decode()
