from decimal import Decimal

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from apps.core.ratelimit import RequestRateLimitMiddleware


def _stub_get_response(request):
    return HttpResponse("ok")


def _make_middleware(*, limit, window_seconds=60, exempt_prefixes=()):
    middleware = RequestRateLimitMiddleware(_stub_get_response)
    middleware.limit = limit
    middleware.window_seconds = window_seconds
    middleware.exempt_prefixes = exempt_prefixes
    return middleware


class TestRequestRateLimitMiddleware:
    """Exercises the middleware directly (not via override_settings) —
    it reads its config once in __init__ for per-request performance, so
    a global settings override wouldn't reach an already-constructed
    instance the way it would for a plain view function."""

    def setup_method(self):
        cache.clear()

    def test_blocks_once_the_limit_is_exceeded_within_the_window(self):
        middleware = _make_middleware(limit=3)
        factory = RequestFactory()

        def hit():
            request = factory.get("/some-view/")
            request.user = AnonymousUser()
            return middleware(request).status_code

        statuses = [hit() for _ in range(5)]
        assert statuses == [200, 200, 200, 429, 429]

    def test_exempt_prefixes_are_never_limited(self):
        middleware = _make_middleware(limit=1, exempt_prefixes=("/healthz",))
        factory = RequestFactory()

        for _ in range(5):
            request = factory.get("/healthz/")
            request.user = AnonymousUser()
            assert middleware(request).status_code == 200

    def test_a_limit_of_zero_disables_rate_limiting(self):
        middleware = _make_middleware(limit=0)
        factory = RequestFactory()

        for _ in range(10):
            request = factory.get("/some-view/")
            request.user = AnonymousUser()
            assert middleware(request).status_code == 200

    def test_fails_open_when_the_cache_backend_errors(self, monkeypatch):
        middleware = _make_middleware(limit=1)

        def _raise(*args, **kwargs):
            raise ConnectionError("cache unreachable")

        monkeypatch.setattr("apps.core.ratelimit.cache.get", _raise)
        factory = RequestFactory()
        request = factory.get("/some-view/")
        request.user = AnonymousUser()

        assert middleware(request).status_code == 200


@pytest.mark.django_db
def test_health_check_reports_ok(client):
    response = client.get(reverse("core:health-check"))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["cache"] == "ok"


@pytest.mark.django_db
def test_correlation_id_is_echoed_on_response(client):
    response = client.get(reverse("core:health-check"), HTTP_X_CORRELATION_ID="abc-123")
    assert response["X-Correlation-ID"] == "abc-123"


@pytest.mark.django_db
def test_correlation_id_is_generated_when_absent(client):
    response = client.get(reverse("core:health-check"))
    assert response["X-Correlation-ID"]  # non-empty, server-generated


@pytest.mark.django_db
class TestSystemHealthMonitorTask:
    """apps.core.tasks.monitor_system_health — the active half of
    monitoring alongside the passive /healthz/ endpoint above."""

    def test_sends_no_alert_when_everything_is_healthy(self, mailoutbox, settings):
        from apps.core.tasks import monitor_system_health

        settings.ADMINS = [("Ops", "ops@example.com")]
        result = monitor_system_health.run()

        assert result["healthy"] is True
        assert len(mailoutbox) == 0

    def test_alerts_admins_when_a_dependency_check_fails(self, mailoutbox, settings, monkeypatch):
        from apps.core import tasks as tasks_module

        settings.ADMINS = [("Ops", "ops@example.com")]
        monkeypatch.setattr(
            tasks_module,
            "run_health_checks",
            lambda: (False, {"database": "error: simulated outage"}),
        )

        result = tasks_module.monitor_system_health.run()

        assert result["healthy"] is False
        assert len(mailoutbox) == 1
        assert "health check failed" in mailoutbox[0].subject
        assert "database" in mailoutbox[0].body
        assert "ops@example.com" in mailoutbox[0].to

    def test_no_admins_configured_is_a_safe_no_op(self, mailoutbox, settings, monkeypatch):
        """mail_admins() with an empty ADMINS list is a documented Django
        no-op — confirms that behavior explicitly rather than assuming it,
        since a raised exception here would be a task failure, not just a
        missed alert."""
        from apps.core import tasks as tasks_module

        settings.ADMINS = []
        monkeypatch.setattr(
            tasks_module,
            "run_health_checks",
            lambda: (False, {"database": "error: simulated outage"}),
        )

        result = tasks_module.monitor_system_health.run()

        assert result["healthy"] is False
        assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_health_monitor_periodic_task_is_seeded_by_migration():
    from django_celery_beat.models import PeriodicTask

    task = PeriodicTask.objects.get(name="Monitor system health")
    assert task.task == "apps.core.tasks.monitor_system_health"
    assert task.enabled is True


class TestEncryptedFields:
    """apps.core.encrypted_fields — the field-level-encryption mechanism
    itself, independent of any one model that uses it. See
    ARCHITECTURE_DECISIONS ADR-032."""

    def test_a_value_round_trips_through_encrypt_and_decrypt(self):
        from apps.core.encrypted_fields import EncryptedTextField

        field = EncryptedTextField()
        ciphertext = field.get_prep_value("Amina Hassan")
        assert ciphertext != "Amina Hassan"
        assert field.from_db_value(ciphertext, None, None) == "Amina Hassan"

    def test_the_same_plaintext_encrypts_differently_each_time(self):
        """Non-determinism is the whole reason .filter(field=x) is
        disallowed below -- confirms that property actually holds."""
        from apps.core.encrypted_fields import EncryptedTextField

        field = EncryptedTextField()
        first = field.get_prep_value("Amina Hassan")
        second = field.get_prep_value("Amina Hassan")
        assert first != second
        assert field.from_db_value(first, None, None) == "Amina Hassan"
        assert field.from_db_value(second, None, None) == "Amina Hassan"

    def test_none_and_empty_string_pass_through_unencrypted(self):
        from apps.core.encrypted_fields import EncryptedTextField

        field = EncryptedTextField()
        assert field.get_prep_value(None) is None
        assert field.get_prep_value("") == ""
        assert field.from_db_value(None, None, None) is None

    def test_a_corrupted_value_reports_unreadable_instead_of_raising(self):
        from apps.core.encrypted_fields import EncryptedTextField

        field = EncryptedTextField()
        assert field.from_db_value("not-valid-ciphertext", None, None) == "[unreadable: decryption failed]"

    def test_exact_lookup_is_rejected_to_avoid_silently_matching_nothing(self):
        from django.core.exceptions import FieldError

        from apps.core.encrypted_fields import EncryptedTextField

        field = EncryptedTextField()
        with pytest.raises(FieldError):
            field.get_lookup("exact")
        with pytest.raises(FieldError):
            field.get_lookup("icontains")

    def test_isnull_lookup_is_still_allowed(self):
        from apps.core.encrypted_fields import EncryptedTextField

        field = EncryptedTextField()
        assert field.get_lookup("isnull") is not None

    def test_char_variant_enforces_max_length_on_plaintext(self):
        from apps.core.encrypted_fields import EncryptedCharField

        field = EncryptedCharField(max_length=5)
        field.get_prep_value("short")  # exactly 5, fine
        with pytest.raises(ValueError):
            field.get_prep_value("too long for five")

    def test_lookup_hash_is_deterministic_and_value_sensitive(self):
        from apps.core.encrypted_fields import compute_lookup_hash

        assert compute_lookup_hash("+255700000001") == compute_lookup_hash("+255700000001")
        assert compute_lookup_hash("+255700000001") != compute_lookup_hash("+255700000002")

    def test_lookup_hash_ignores_surrounding_whitespace(self):
        from apps.core.encrypted_fields import compute_lookup_hash

        assert compute_lookup_hash("  Amina Hassan  ") == compute_lookup_hash("Amina Hassan")


class TestKusanyaUiTemplateTags:
    """apps.core.templatetags.kusanya_ui — backs the design system's
    active-nav-link, status-badge, and pagination/sort link conventions.
    See docs/DESIGN_SYSTEM.md."""

    def test_is_active_ns_matches_current_namespace(self):
        from apps.core.templatetags.kusanya_ui import is_active_ns

        class _Resolver:
            app_name = "customers"

        class _Request:
            resolver_match = _Resolver()

        assert is_active_ns({"request": _Request()}, "customers") == "active"
        assert is_active_ns({"request": _Request()}, "billing") == ""
        assert is_active_ns({"request": _Request()}, "billing", "customers") == "active"

    def test_is_active_ns_is_safe_with_no_resolver_match(self):
        from apps.core.templatetags.kusanya_ui import is_active_ns

        class _Request:
            resolver_match = None

        assert is_active_ns({"request": _Request()}, "customers") == ""
        assert is_active_ns({}, "customers") == ""

    def test_aria_current_ns_matches_namespace_or_view_name(self):
        from apps.core.templatetags.kusanya_ui import aria_current_ns

        class _Resolver:
            app_name = "customers"
            view_name = "customers:list"

        class _Request:
            resolver_match = _Resolver()

        assert str(aria_current_ns({"request": _Request()}, "customers")) == 'aria-current="page"'
        assert str(aria_current_ns({"request": _Request()}, "core:background-jobs")) == ""
        # matches by exact view_name too, not just namespace -- for links
        # sharing a namespace with other pages (core:background-jobs vs
        # core:dashboard-router)
        assert str(aria_current_ns({"request": _Request()}, "customers:list")) == 'aria-current="page"'

    def test_aria_current_ns_is_safe_with_no_resolver_match(self):
        from apps.core.templatetags.kusanya_ui import aria_current_ns

        class _Request:
            resolver_match = None

        assert aria_current_ns({"request": _Request()}, "customers") == ""
        assert aria_current_ns({}, "customers") == ""

    @pytest.mark.parametrize(
        "status,expected",
        [
            ("active", "text-bg-success"),
            ("SUCCESSFUL", "text-bg-success"),
            ("pending", "text-bg-warning"),
            ("failed", "text-bg-danger"),
            ("refunded", "text-bg-info"),
            ("some_unknown_status", "text-bg-secondary"),
        ],
    )
    def test_status_badge_class_maps_known_vocabulary(self, status, expected):
        from apps.core.templatetags.kusanya_ui import status_badge_class

        assert status_badge_class(status) == expected

    def test_querystring_with_preserves_other_params_and_overrides_given_ones(self, rf):
        from apps.core.templatetags.kusanya_ui import querystring_with

        request = rf.get("/customers/?q=amina&sort=-created_at")
        result = querystring_with({"request": request}, page=2)
        assert "q=amina" in result
        assert "sort=-created_at" in result
        assert "page=2" in result

    def test_querystring_with_removes_a_key_when_set_to_none(self, rf):
        from apps.core.templatetags.kusanya_ui import querystring_with

        request = rf.get("/customers/?q=amina&page=3")
        result = querystring_with({"request": request}, page=None)
        assert "page" not in result
        assert "q=amina" in result


@pytest.mark.django_db
class TestTopbarAlertsContextProcessor:
    """apps.core.context_processors.topbar_alerts -- the notification
    bell backs genuinely real, live-computed state (open reconciliation
    exceptions, pending tenant approvals), never a fabricated feed. See
    docs/DESIGN_SYSTEM.md's "Notifications" section."""

    def test_no_alerts_when_nothing_needs_attention(self, client, make_user, make_tenant, make_membership):
        from apps.accounts.models import MFADevice

        tenant = make_tenant()
        user = make_user(email="quiet@example.com")
        MFADevice.objects.create(user=user, confirmed=True)  # isolate this test from the MFA nudge (see below)
        make_membership(user, tenant)
        client.force_login(user)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()

        response = client.get("/customers/")

        assert response.context["topbar_alerts"] == []

    def test_open_reconciliation_exception_surfaces_as_a_real_alert(
        self, client, make_user, make_tenant, make_membership, make_bill_with_control_number, mock_provider
    ):
        from apps.accounts.models import MFADevice
        from apps.payments.models import Payment
        from apps.reconciliation.models import ExceptionStatus, ExceptionType, ReconciliationException

        tenant = make_tenant()
        user = make_user(email="ops@example.com")
        MFADevice.objects.create(user=user, confirmed=True)  # isolate this test from the MFA nudge (see below)
        make_membership(user, tenant)
        client.force_login(user)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()

        _, control_number = make_bill_with_control_number(tenant)
        payment = Payment.objects.create(
            tenant=tenant, control_number=control_number, provider=mock_provider, amount=Decimal("500000")
        )
        ReconciliationException.objects.create(
            tenant=tenant, payment=payment, status=ExceptionStatus.OPEN,
            exception_type=ExceptionType.STUCK_UNKNOWN,
        )

        response = client.get("/customers/")

        alerts = response.context["topbar_alerts"]
        assert len(alerts) == 1
        assert "1 open reconciliation exception" in alerts[0]["text"]

    def test_mfa_not_enabled_surfaces_as_a_nudge(self, client, make_user, make_tenant, make_membership):
        tenant = make_tenant()
        user = make_user(email="no-mfa@example.com")
        make_membership(user, tenant)
        client.force_login(user)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()

        response = client.get("/customers/")

        alerts = response.context["topbar_alerts"]
        assert len(alerts) == 1
        assert alerts[0]["url_name"] == "accounts:mfa-status"

    def test_mfa_nudge_disappears_once_confirmed(self, client, make_user, make_tenant, make_membership):
        from apps.accounts.models import MFADevice

        tenant = make_tenant()
        user = make_user(email="has-mfa@example.com")
        MFADevice.objects.create(user=user, confirmed=True)
        make_membership(user, tenant)
        client.force_login(user)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()

        response = client.get("/customers/")

        assert all(a["url_name"] != "accounts:mfa-status" for a in response.context["topbar_alerts"])

    def test_pending_tenant_surfaces_only_for_platform_staff(
        self, client, make_user, make_tenant, make_membership, make_platform_role
    ):
        from apps.tenants.models import Tenant
        from apps.users.models import PlatformRole

        tenant = make_tenant()
        Tenant.objects.create(name="Awaiting Co", contact_email="a@example.com", status=Tenant.Status.PENDING)
        user = make_user(email="staffmember@example.com")
        user.is_staff = True
        user.save()
        make_membership(user, tenant)
        make_platform_role(user, role=PlatformRole.OPERATIONS_ADMIN)
        client.force_login(user)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()

        response = client.get("/customers/")

        alerts = response.context["topbar_alerts"]
        assert any("awaiting approval" in a["text"] for a in alerts)

    def test_anonymous_requests_get_no_alerts_key_populated(self, client):
        response = client.get("/accounts/login/")
        # context processor returns {} for anonymous -- no KeyError, no crash
        assert response.status_code == 200


@pytest.mark.django_db
class TestCommandPaletteSearch:
    """apps.core.views.command_palette_search -- real navigation
    shortcuts + real entity search, never fabricated results. See
    docs/DESIGN_SYSTEM.md's "Command palette" section."""

    def _login(self, client, make_user, make_tenant, make_membership):
        tenant = make_tenant()
        user = make_user(email="palette@example.com")
        make_membership(user, tenant)
        client.force_login(user)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()
        return tenant

    def test_empty_query_returns_the_prompt_not_an_error(self, client, make_user, make_tenant, make_membership):
        self._login(client, make_user, make_tenant, make_membership)
        response = client.get("/command-palette/search/")
        assert response.status_code == 200
        assert b"Type to search" in response.content

    def test_nav_shortcut_matches_by_label(self, client, make_user, make_tenant, make_membership):
        self._login(client, make_user, make_tenant, make_membership)
        response = client.get("/command-palette/search/", {"q": "Customers"})
        assert response.status_code == 200
        assert b"Customers" in response.content

    def test_exact_customer_name_match_is_found(self, client, make_user, make_tenant, make_membership):
        from apps.customers.models import Customer

        tenant = self._login(client, make_user, make_tenant, make_membership)
        Customer.objects.create(tenant=tenant, full_name="Amina Juma")

        response = client.get("/command-palette/search/", {"q": "Amina Juma"})

        assert b"Amina Juma" in response.content

    def test_bill_number_substring_match_is_found(
        self, client, make_user, make_tenant, make_membership, make_customer, make_customer_account
    ):
        from decimal import Decimal

        from apps.billing.services import get_or_create_bill

        tenant = self._login(client, make_user, make_tenant, make_membership)
        account = make_customer_account(tenant, make_customer(tenant))
        bill, _ = get_or_create_bill(
            tenant=tenant, customer_account=account,
            items=[{"description": "Fee", "unit_amount": Decimal("100")}],
        )

        response = client.get("/command-palette/search/", {"q": bill.bill_number[:6]})

        assert bill.bill_number.encode() in response.content

    def test_no_match_shows_a_real_no_results_message(self, client, make_user, make_tenant, make_membership):
        self._login(client, make_user, make_tenant, make_membership)
        response = client.get("/command-palette/search/", {"q": "zzz-nonexistent-zzz"})
        assert b"No matches" in response.content


@pytest.mark.django_db
class TestBackgroundJobsPage:
    """apps.core.views.background_jobs -- real aggregated state from
    WebhookDelivery/Notification, never fabricated counts."""

    def test_renders_with_zero_counts_when_nothing_has_happened(
        self, client, make_user, make_tenant, make_membership
    ):
        tenant = make_tenant()
        user = make_user(email="ops-jobs@example.com")
        make_membership(user, tenant)
        client.force_login(user)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()

        response = client.get("/background-jobs/")

        assert response.status_code == 200
        assert response.context["webhook_pending"] == 0
        assert response.context["notification_sent"] == 0

    def test_staff_user_also_sees_scheduled_tasks(self, client, make_user, make_tenant, make_membership):
        tenant = make_tenant()
        user = make_user(email="staffops@example.com")
        user.is_staff = True
        user.save()
        make_membership(user, tenant)
        client.force_login(user)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()

        response = client.get("/background-jobs/")

        assert response.status_code == 200
        assert "scheduled_tasks" in response.context
        # Seeded by apps/core/migrations/0002_seed_health_monitor_schedule.py
        names = [t.name for t in response.context["scheduled_tasks"]]
        assert "Monitor system health" in names

    def test_non_staff_user_does_not_see_scheduled_tasks(
        self, client, make_user, make_tenant, make_membership
    ):
        tenant = make_tenant()
        user = make_user(email="regular@example.com")
        make_membership(user, tenant)
        client.force_login(user)
        session = client.session
        session["active_tenant_id"] = str(tenant.id)
        session.save()

        response = client.get("/background-jobs/")

        assert "scheduled_tasks" not in response.context
