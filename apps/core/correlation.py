"""Correlation ID storage shared by middleware, logging, and audit.

A single contextvar holds the current request's correlation ID so any code
running during that request/task can log or record it without threading it
through every function signature.
"""

import contextvars
import uuid

_correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="-"
)

HEADER_NAME = "X-Correlation-ID"


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def set_correlation_id(value: str) -> None:
    _correlation_id_var.set(value)


def get_correlation_id() -> str:
    return _correlation_id_var.get()
