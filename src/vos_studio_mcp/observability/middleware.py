"""FastAPI middleware for correlation IDs."""

from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response

from vos_studio_mcp.observability.context import request_id_var, trace_id_var


async def correlation_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Attach request and trace IDs to request context and response headers."""

    trace_id = request.headers.get("x-trace-id") or str(uuid4())
    request_id = request.headers.get("x-request-id") or str(uuid4())

    trace_token = trace_id_var.set(trace_id)
    request_token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
        response.headers["x-trace-id"] = trace_id
        response.headers["x-request-id"] = request_id
        return response
    finally:
        trace_id_var.reset(trace_token)
        request_id_var.reset(request_token)
