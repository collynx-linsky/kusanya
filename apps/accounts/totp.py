"""
TOTP (RFC 6238, built on HOTP/RFC 4226) implemented directly against the
standard library — no `pyotp`/`django-otp` dependency. The algorithm is
~30 lines of well-specified HMAC-SHA1 arithmetic; pulling in a dependency
for it would trade a small, auditable, test-covered implementation for an
opaque one, for no real benefit. Compatible with any standard
authenticator app (Google Authenticator, Authy, 1Password, etc.) — they
all implement exactly this RFC.
"""

import base64
import hashlib
import hmac
import os
import struct
import time
import urllib.parse

DIGITS = 6
PERIOD_SECONDS = 30
VALID_WINDOW = 1  # accept one period before/after, to tolerate clock drift


def generate_secret() -> str:
    """A fresh base32 secret — the format every authenticator app expects
    for manual entry or an otpauth:// URI."""
    return base64.b32encode(os.urandom(20)).decode("ascii")


def _hotp(secret_b32: str, counter: int) -> str:
    padding = "=" * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode(secret_b32.upper() + padding)
    message = struct.pack(">Q", counter)
    digest = hmac.new(key, message, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**DIGITS)).zfill(DIGITS)


def generate_totp(secret_b32: str, *, for_time: float | None = None) -> str:
    counter = int((for_time if for_time is not None else time.time()) // PERIOD_SECONDS)
    return _hotp(secret_b32, counter)


def verify_totp(secret_b32: str, code: str, *, valid_window: int = VALID_WINDOW) -> bool:
    """Constant-time comparison against the current code and a small
    window of adjacent periods (clock drift tolerance) — never a plain
    `==`, same rule as every other secret comparison in this codebase
    (apps.core.signing)."""
    if not code or not code.strip().isdigit():
        return False
    code = code.strip()
    now = time.time()
    for offset in range(-valid_window, valid_window + 1):
        candidate = generate_totp(secret_b32, for_time=now + offset * PERIOD_SECONDS)
        if hmac.compare_digest(candidate, code):
            return True
    return False


def build_otpauth_uri(*, secret_b32: str, account_name: str, issuer: str = "KUSANYA") -> str:
    """`otpauth://` URI an authenticator app can import directly (via QR
    code or, since Phase 7 doesn't generate a QR image — see
    ARCHITECTURE_DECISIONS ADR-025 — via manual "enter a setup URI" if the
    app supports it; the raw secret is always shown too, for apps that
    only support manual entry)."""
    label = urllib.parse.quote(f"{issuer}:{account_name}")
    params = urllib.parse.urlencode(
        {"secret": secret_b32, "issuer": issuer, "algorithm": "SHA1", "digits": DIGITS, "period": PERIOD_SECONDS}
    )
    return f"otpauth://totp/{label}?{params}"
