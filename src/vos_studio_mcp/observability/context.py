"""Correlation context for logs and request handling."""

from contextvars import ContextVar

trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_trace_id() -> str | None:
    """Return the active trace ID, if one is set."""

    return trace_id_var.get()


def get_request_id() -> str | None:
    """Return the active request ID, if one is set."""

    return request_id_var.get()
