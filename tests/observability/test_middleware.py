"""Unit tests for correlation_middleware."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vos_studio_mcp.observability.context import request_id_var, trace_id_var


def _make_app() -> FastAPI:
    from vos_studio_mcp.observability.middleware import correlation_middleware

    app = FastAPI()
    app.middleware("http")(correlation_middleware)

    @app.get("/ping")
    async def ping() -> dict:
        return {
            "trace_id": trace_id_var.get(),
            "request_id": request_id_var.get(),
        }

    return app


def test_middleware_generates_ids_when_headers_absent() -> None:
    client = TestClient(_make_app())
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert "x-trace-id" in resp.headers
    assert "x-request-id" in resp.headers
    assert len(resp.headers["x-trace-id"]) == 36
    assert len(resp.headers["x-request-id"]) == 36


def test_middleware_uses_provided_headers() -> None:
    client = TestClient(_make_app())
    resp = client.get("/ping", headers={"x-trace-id": "trace-abc", "x-request-id": "req-xyz"})
    assert resp.status_code == 200
    assert resp.headers["x-trace-id"] == "trace-abc"
    assert resp.headers["x-request-id"] == "req-xyz"


def test_middleware_sets_context_vars_for_route() -> None:
    client = TestClient(_make_app())
    resp = client.get("/ping", headers={"x-trace-id": "my-trace", "x-request-id": "my-req"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["trace_id"] == "my-trace"
    assert body["request_id"] == "my-req"


def test_middleware_unique_ids_per_request() -> None:
    client = TestClient(_make_app())
    resp1 = client.get("/ping")
    resp2 = client.get("/ping")
    assert resp1.headers["x-trace-id"] != resp2.headers["x-trace-id"]
    assert resp1.headers["x-request-id"] != resp2.headers["x-request-id"]


def test_middleware_partial_headers_generates_missing() -> None:
    client = TestClient(_make_app())
    resp = client.get("/ping", headers={"x-trace-id": "provided-trace"})
    assert resp.headers["x-trace-id"] == "provided-trace"
    assert "x-request-id" in resp.headers
    assert len(resp.headers["x-request-id"]) == 36
