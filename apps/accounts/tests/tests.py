import time

import pytest

from apps.accounts.models import BackupCode, MFADevice
from apps.accounts.throttle import is_locked_out, record_failure, reset
from apps.accounts.totp import build_otpauth_qr_svg, build_otpauth_uri, generate_secret, generate_totp, verify_totp


class TestTotpAlgorithm:
    """Pure algorithm tests — no database needed."""

    def test_generated_code_is_six_digits(self):
        secret = generate_secret()
        code = generate_totp(secret)
        assert len(code) == 6
        assert code.isdigit()

    def test_a_freshly_generated_code_verifies(self):
        secret = generate_secret()
        code = generate_totp(secret)
        assert verify_totp(secret, code) is True

    def test_wrong_code_does_not_verify(self):
        secret = generate_secret()
        real_code = generate_totp(secret)
        wrong_code = "000000" if real_code != "000000" else "111111"
        assert verify_totp(secret, wrong_code) is False

    def test_code_for_a_different_secret_does_not_verify(self):
        secret_a = generate_secret()
        secret_b = generate_secret()
        code_for_a = generate_totp(secret_a)
        # Astronomically unlikely to collide, but guard against test flakiness.
        if generate_totp(secret_b) == code_for_a:
            pytest.skip("Coincidental code collision between two random secrets.")
        assert verify_totp(secret_b, code_for_a) is False

    def test_a_code_from_one_period_ago_still_verifies_within_the_drift_window(self):
        secret = generate_secret()
        past_code = generate_totp(secret, for_time=time.time() - 30)
        assert verify_totp(secret, past_code) is True

    def test_a_code_from_far_in_the_past_does_not_verify(self):
        secret = generate_secret()
        old_code = generate_totp(secret, for_time=time.time() - 3600)
        assert verify_totp(secret, old_code) is False

    def test_non_numeric_input_never_verifies(self):
        secret = generate_secret()
        assert verify_totp(secret, "abcdef") is False
        assert verify_totp(secret, "") is False
        assert verify_totp(secret, None) is False

    def test_otpauth_uri_contains_the_secret_and_issuer(self):
        secret = generate_secret()
        uri = build_otpauth_uri(secret_b32=secret, account_name="amina@example.com")
        assert uri.startswith("otpauth://totp/")
        assert secret in uri
        assert "KUSANYA" in uri

    def test_qr_svg_is_well_formed_svg_markup(self):
        secret = generate_secret()
        uri = build_otpauth_uri(secret_b32=secret, account_name="amina@example.com")
        svg = build_otpauth_qr_svg(uri)
        assert "<svg" in svg
        assert "</svg>" in svg


@pytest.mark.django_db
class TestMfaLifecycle:
    def test_confirming_with_a_valid_code_activates_the_device(self, make_user):
        from apps.accounts.mfa_services import confirm_device

        user = make_user()
        device = MFADevice.objects.create(user=user)
        code = generate_totp(device.secret)

        result = confirm_device(device, code)

        assert result is True
        device.refresh_from_db()
        assert device.confirmed is True

    def test_confirming_with_an_invalid_code_does_not_activate(self, make_user):
        from apps.accounts.mfa_services import confirm_device

        user = make_user()
        device = MFADevice.objects.create(user=user)

        result = confirm_device(device, "000000")

        assert result is False
        device.refresh_from_db()
        assert device.confirmed is False

    def test_backup_codes_are_single_use(self, make_user):
        from apps.accounts.mfa_services import consume_backup_code, generate_backup_codes

        user = make_user()
        codes = generate_backup_codes(user)
        first_code = codes[0]

        assert consume_backup_code(user, first_code) is True
        assert consume_backup_code(user, first_code) is False  # already used

    def test_regenerating_backup_codes_invalidates_the_old_set(self, make_user):
        from apps.accounts.mfa_services import consume_backup_code, generate_backup_codes

        user = make_user()
        old_codes = generate_backup_codes(user)
        generate_backup_codes(user)  # regenerate

        assert consume_backup_code(user, old_codes[0]) is False
        assert BackupCode.objects.filter(user=user).count() == 10

    def test_disable_mfa_removes_device_and_backup_codes(self, make_user):
        from apps.accounts.mfa_services import disable_mfa, generate_backup_codes

        user = make_user()
        MFADevice.objects.create(user=user, confirmed=True)
        generate_backup_codes(user)

        disable_mfa(user)

        assert not MFADevice.objects.filter(user=user).exists()
        assert not BackupCode.objects.filter(user=user).exists()

    def test_setup_page_renders_a_scannable_qr_code(self, client, make_user):
        user = make_user(email="qrsetup@example.com", password="Str0ngPassw0rd!")
        client.force_login(user)

        response = client.get("/accounts/mfa/setup/")

        assert response.status_code == 200
        content = response.content.decode()
        assert "<svg" in content
        assert "</svg>" in content


@pytest.mark.django_db
class TestLoginWithMfa:
    def test_user_without_mfa_logs_in_directly(self, client, make_user):
        user = make_user(email="nomfa@example.com", password="Str0ngPassw0rd!")
        response = client.post(
            "/accounts/login/", {"username": "nomfa@example.com", "password": "Str0ngPassw0rd!"}
        )
        assert response.status_code == 302
        assert response.url != "/accounts/mfa/verify/"

        # session should already be authenticated
        response2 = client.get("/accounts/mfa/")
        assert response2.status_code == 200  # logged in, can view own MFA status page

    def test_user_with_confirmed_mfa_is_redirected_to_verify_and_not_logged_in_yet(self, client, make_user):
        user = make_user(email="hasmfa@example.com", password="Str0ngPassw0rd!")
        device = MFADevice.objects.create(user=user, confirmed=True)

        response = client.post(
            "/accounts/login/", {"username": "hasmfa@example.com", "password": "Str0ngPassw0rd!"}
        )
        assert response.status_code == 302
        assert response.url == "/accounts/mfa/verify/"

        # Not actually logged in yet — a page requiring auth should redirect to login.
        dashboard_response = client.get("/dashboard/")
        assert dashboard_response.status_code == 302
        assert "/accounts/login/" in dashboard_response.url

    def test_correct_totp_code_completes_login(self, client, make_user):
        user = make_user(email="mfalogin@example.com", password="Str0ngPassw0rd!")
        device = MFADevice.objects.create(user=user, confirmed=True)
        client.post("/accounts/login/", {"username": "mfalogin@example.com", "password": "Str0ngPassw0rd!"})

        code = generate_totp(device.secret)
        response = client.post("/accounts/mfa/verify/", {"code": code})

        assert response.status_code == 302
        dashboard_response = client.get("/dashboard/")
        assert dashboard_response.status_code == 200  # now actually logged in

    def test_wrong_totp_code_does_not_complete_login(self, client, make_user):
        user = make_user(email="mfawrong@example.com", password="Str0ngPassw0rd!")
        MFADevice.objects.create(user=user, confirmed=True)
        client.post("/accounts/login/", {"username": "mfawrong@example.com", "password": "Str0ngPassw0rd!"})

        client.post("/accounts/mfa/verify/", {"code": "000000"})

        dashboard_response = client.get("/dashboard/")
        assert dashboard_response.status_code == 302  # still not logged in

    def test_backup_code_completes_login_and_is_then_used_up(self, client, make_user):
        from apps.accounts.mfa_services import generate_backup_codes

        user = make_user(email="mfabackup@example.com", password="Str0ngPassw0rd!")
        MFADevice.objects.create(user=user, confirmed=True)
        codes = generate_backup_codes(user)

        client.post("/accounts/login/", {"username": "mfabackup@example.com", "password": "Str0ngPassw0rd!"})
        response = client.post("/accounts/mfa/verify/", {"code": codes[0]})
        assert response.status_code == 302

        dashboard_response = client.get("/dashboard/")
        assert dashboard_response.status_code == 200

        assert BackupCode.objects.filter(user=user, used_at__isnull=False).count() == 1


@pytest.mark.django_db
class TestLoginThrottle:
    def test_repeated_failures_lock_out_further_attempts(self, client, make_user):
        make_user(email="lockout@example.com", password="Str0ngPassw0rd!")

        for _ in range(5):
            client.post("/accounts/login/", {"username": "lockout@example.com", "password": "wrong-password"})

        # Even the CORRECT password is now rejected outright.
        response = client.post(
            "/accounts/login/", {"username": "lockout@example.com", "password": "Str0ngPassw0rd!"}
        )
        dashboard_response = client.get("/dashboard/")
        assert dashboard_response.status_code == 302  # not logged in — locked out

    def test_successful_login_resets_the_throttle_counter(self):
        record_failure("login", "1.2.3.4:test@example.com")
        record_failure("login", "1.2.3.4:test@example.com")
        reset("login", "1.2.3.4:test@example.com")
        assert is_locked_out("login", "1.2.3.4:test@example.com") is False
