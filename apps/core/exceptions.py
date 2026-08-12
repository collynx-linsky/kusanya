"""
Consistent error shape for both the (future) REST API and server-rendered
error pages. See docs/API_ARCHITECTURE.md and section 45 of the build spec.

Every handled error exposes: an error code, a human-readable message, the
request's correlation ID, and the appropriate HTTP status. Stack traces are
never exposed to end users outside DEBUG.
"""

import logging

from rest_framework.views import exception_handler as drf_default_exception_handler

from apps.core.correlation import get_correlation_id

logger = logging.getLogger("kusanya")


class KusanyaError(Exception):
    """Base class for domain errors that carry a stable machine-readable code."""

    code = "error"
    message = "An unexpected error occurred."
    status_code = 500

    def __init__(self, message: str | None = None, code: str | None = None):
        self.message = message or self.message
        self.code = code or self.code
        super().__init__(self.message)


class NotFoundError(KusanyaError):
    code = "not_found"
    status_code = 404


class ValidationFailedError(KusanyaError):
    code = "validation_failed"
    status_code = 400


class PermissionDeniedError(KusanyaError):
    code = "permission_denied"
    status_code = 403


class ConflictError(KusanyaError):
    """Raised for state-conflict situations, e.g. idempotency mismatches."""

    code = "conflict"
    status_code = 409


def drf_exception_handler(exc, context):
    """Wraps DRF's default handler to emit KUSANYA's standard error envelope."""
    response = drf_default_exception_handler(exc, context)

    if isinstance(exc, KusanyaError):
        from rest_framework.response import Response

        return Response(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "correlation_id": get_correlation_id(),
                }
            },
            status=exc.status_code,
        )

    if response is not None:
        response.data = {
            "error": {
                "code": getattr(exc, "default_code", "error"),
                "message": response.data,
                "correlation_id": get_correlation_id(),
            }
        }
        return response

    logger.exception("Unhandled exception", exc_info=exc)
    return None
