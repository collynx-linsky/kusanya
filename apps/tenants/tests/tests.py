"""
Tenant isolation and RBAC are the two invariants this platform cannot ship
without (build spec sections 7 and 8) — these tests exist to fail loudly
the moment either is violated.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.tenants.middleware import TenantResolutionMiddleware
from apps.tenants.models import Tenant, TenantMembership, TenantRole
from apps.tenants.permissions import (
    get_tenant_role,
    has_platform_role,
    has_tenant_role,
    require_tenant_role,
)
from apps.users.models import PlatformRole

User = get_user_model()


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


@pytest.mark.django_db
class TestTeamManagement:
    """apps.tenants.views.team_members/team_member_create -- the
    "add a colleague" gap TenantMembership.invited_by was built for
    but never had a UI, per ARCHITECTURE_DECISIONS ADR-043."""

    def _login_as_admin(self, client, make_user, make_tenant, make_membership):
        tenant = make_tenant()
        admin = make_user(email="team-admin@example.com")
        make_membership(admin, tenant, role=TenantRole.ADMIN)
        client.force_login(admin)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()
        return tenant, admin

    def test_viewer_cannot_add_a_teammate(self, client, make_user, make_tenant, make_membership):
        tenant = make_tenant()
        viewer = make_user(email="viewer@example.com")
        make_membership(viewer, tenant, role=TenantRole.VIEWER)
        client.force_login(viewer)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()

        response = client.post(
            reverse("tenants:team-member-create"),
            {
                "first_name": "Should",
                "last_name": "Fail",
                "email": "shouldfail@example.com",
                "password": "SuperSecurePass123!",
                "role": TenantRole.VIEWER,
            },
        )
        assert response.status_code == 403
        assert not User.objects.filter(email="shouldfail@example.com").exists()

    def test_admin_can_add_a_teammate(self, client, make_user, make_tenant, make_membership):
        tenant, admin = self._login_as_admin(client, make_user, make_tenant, make_membership)

        response = client.post(
            reverse("tenants:team-member-create"),
            {
                "first_name": "Peter",
                "last_name": "Lyimo",
                "email": "peter@example.com",
                "password": "SuperSecurePass123!",
                "role": TenantRole.BILLING_OFFICER,
            },
        )
        assert response.status_code == 302

        new_user = User.objects.get(email="peter@example.com")
        membership = TenantMembership.objects.get(user=new_user, tenant=tenant)
        assert membership.role == TenantRole.BILLING_OFFICER
        assert membership.invited_by == admin
        assert membership.is_active is True

    def test_duplicate_email_is_rejected(self, client, make_user, make_tenant, make_membership):
        self._login_as_admin(client, make_user, make_tenant, make_membership)
        make_user(email="already-exists@example.com")

        response = client.post(
            reverse("tenants:team-member-create"),
            {
                "first_name": "Dup",
                "last_name": "Licate",
                "email": "already-exists@example.com",
                "password": "SuperSecurePass123!",
                "role": TenantRole.VIEWER,
            },
        )
        assert response.status_code == 200
        assert "already exists" in response.content.decode()

    def test_admin_can_deactivate_and_reactivate_a_teammate(
        self, client, make_user, make_tenant, make_membership
    ):
        tenant, admin = self._login_as_admin(client, make_user, make_tenant, make_membership)
        teammate = make_user(email="teammate@example.com")
        membership = make_membership(teammate, tenant, role=TenantRole.VIEWER)

        response = client.post(reverse("tenants:team-member-deactivate", args=[membership.pk]))
        assert response.status_code == 302
        membership.refresh_from_db()
        assert membership.is_active is False

        response = client.post(reverse("tenants:team-member-activate", args=[membership.pk]))
        assert response.status_code == 302
        membership.refresh_from_db()
        assert membership.is_active is True

    def test_admin_cannot_deactivate_their_own_membership(
        self, client, make_user, make_tenant, make_membership
    ):
        tenant, admin = self._login_as_admin(client, make_user, make_tenant, make_membership)
        own_membership = TenantMembership.objects.get(user=admin, tenant=tenant)

        response = client.post(reverse("tenants:team-member-deactivate", args=[own_membership.pk]))
        assert response.status_code == 302
        own_membership.refresh_from_db()
        assert own_membership.is_active is True

    def test_team_list_shows_only_this_tenants_members(
        self, client, make_user, make_tenant, make_membership
    ):
        tenant, admin = self._login_as_admin(client, make_user, make_tenant, make_membership)
        other_tenant = make_tenant(name="A Different Institution")
        other_user = make_user(email="other-tenant-user@example.com")
        make_membership(other_user, other_tenant, role=TenantRole.VIEWER)

        response = client.get(reverse("tenants:team"))
        assert response.status_code == 200
        body = response.content.decode()
        assert admin.email in body
        assert other_user.email not in body
