"""
Webhook payload signing. A receiving tenant system verifies a delivery by
recomputing this same signature with its own copy of the endpoint's
secret — see docs/WEBHOOK_ARCHITECTURE.md for the receiver-side recipe.
"""

import json

from apps.core.signing import sign, verify


def canonical_body(payload: dict) -> bytes:
    """Deterministic JSON serialization — sorted keys, no extra
    whitespace — so the sender and an independently-implemented receiver
    compute the same bytes to sign/verify."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def build_signature(secret: str, timestamp: str, body: bytes) -> str:
    return sign(secret, f"{timestamp}.{body.decode('utf-8')}")


def verify_signature(secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    return verify(secret, f"{timestamp}.{body.decode('utf-8')}", signature)
