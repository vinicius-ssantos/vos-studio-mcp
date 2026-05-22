"""Celery task base class with correlation context propagation (ADR-0030)."""

from typing import Any

from celery import Task

from vos_studio_mcp.observability.context import (
    request_id_var,
    trace_id_var,
)


class CorrelatedTask(Task):  # type: ignore[misc]
    """Propagates trace_id and request_id from the dispatch site into the worker.

    When a task is dispatched, the current ContextVar values are injected into
    Celery task headers. On the worker side, __call__ extracts those headers and
    restores the ContextVars before the task body runs, so all log records emitted
    inside the task carry the originating request's correlation IDs.
    """

    abstract = True

    def apply_async(self, args: Any = None, kwargs: Any = None, **options: Any) -> Any:
        headers: dict[str, str] = dict(options.pop("headers", None) or {})
        trace = trace_id_var.get()
        request_id = request_id_var.get()
        if trace is not None:
            headers["trace_id"] = trace
        if request_id is not None:
            headers["request_id"] = request_id
        return super().apply_async(args, kwargs, headers=headers, **options)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raw_headers = getattr(self.request, "headers", None) or {}
        trace = raw_headers.get("trace_id")
        request_id = raw_headers.get("request_id")

        token_trace = trace_id_var.set(trace)
        token_request = request_id_var.set(request_id)
        try:
            return super().__call__(*args, **kwargs)
        finally:
            trace_id_var.reset(token_trace)
            request_id_var.reset(token_request)
