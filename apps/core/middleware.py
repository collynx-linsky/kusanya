from apps.core.correlation import HEADER_NAME, get_correlation_id, new_correlation_id, set_correlation_id


class CorrelationIdMiddleware:
    """Assigns a correlation ID to every request.

    Reuses an inbound X-Correlation-ID header when a caller (e.g. an ERP
    integration, later phases) already supplied one, so a single logical
    operation can be traced across systems. Always echoes it back on the
    response.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        correlation_id = request.headers.get(HEADER_NAME) or new_correlation_id()
        set_correlation_id(correlation_id)
        request.correlation_id = correlation_id

        response = self.get_response(request)

        response[HEADER_NAME] = correlation_id
        return response
