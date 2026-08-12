"""Request context (IP, user agent) available without threading `request`
through every function that might need to audit-log something."""

import contextvars

_request_context_var: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "audit_request_context", default={}
)


def set_request_context(*, ip_address: str | None, user_agent: str) -> None:
    _request_context_var.set({"ip_address": ip_address, "user_agent": user_agent})


def get_request_context() -> dict:
    return _request_context_var.get()


def client_ip_from_request(request) -> str | None:
    # Trusts X-Forwarded-For only because production.py's
    # SECURE_PROXY_SSL_HEADER setup assumes a trusted reverse proxy is the
    # only thing that can set it; do not relax that assumption without also
    # locking down which hosts may set the header.
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
