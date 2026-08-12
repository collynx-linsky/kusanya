import logging

from apps.core.correlation import get_correlation_id


class CorrelationIdFilter(logging.Filter):
    """Injects the current request's correlation ID into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()
        return True
