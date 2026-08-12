"""
Shared HMAC-SHA256 signing/verification — used both for inbound provider
callback signature checks (apps.providers) and outbound webhook delivery
(apps.webhooks), so there is exactly one place that gets this right.

Never use `==` to compare signatures — timing attacks. Always
`hmac.compare_digest`.
"""

import hmac
from hashlib import sha256


def sign(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), sha256).hexdigest()


def verify(secret: str, message: str, signature: str) -> bool:
    if not signature:
        return False
    expected = sign(secret, message)
    return hmac.compare_digest(expected, signature)
