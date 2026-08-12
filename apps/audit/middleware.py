from apps.audit.context import client_ip_from_request, set_request_context


class AuditContextMiddleware:
    """Captures IP/user-agent for the duration of the request so
    `record_audit_event` can be called from deep in a service layer
    without every call site plumbing `request` through."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_request_context(
            ip_address=client_ip_from_request(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        return self.get_response(request)
