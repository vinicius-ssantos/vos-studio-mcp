"""Tests for Prometheus /metrics endpoint and metrics helpers (Issue #30)."""

from fastapi.testclient import TestClient


class TestMetricsEndpoint:
    def test_metrics_returns_200(self) -> None:
        from vos_studio_mcp.server import app

        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/metrics")
        assert resp.status_code == 200

    def test_metrics_content_type_is_prometheus(self) -> None:
        from vos_studio_mcp.server import app

        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/metrics")
        assert "text/plain" in resp.headers["content-type"]

    def test_metrics_contains_expected_metric_names(self) -> None:
        from vos_studio_mcp.server import app

        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/metrics")

        body = resp.text
        assert "vos_http_requests_total" in body
        assert "vos_http_request_duration_seconds" in body
        assert "vos_provider_calls_total" in body
        assert "vos_circuit_breaker_open" in body
        assert "vos_mcp_tool_calls_total" in body


class TestMetricsHelpers:
    def test_record_provider_call_success(self) -> None:

        from vos_studio_mcp.observability.metrics import PROVIDER_CALLS, record_provider_call

        before = _get_counter(PROVIDER_CALLS, provider="higgsfield", operation="generate", status="success")
        record_provider_call("higgsfield", "generate", success=True)
        after = _get_counter(PROVIDER_CALLS, provider="higgsfield", operation="generate", status="success")
        assert after == before + 1

    def test_record_provider_call_error(self) -> None:
        from vos_studio_mcp.observability.metrics import PROVIDER_CALLS, record_provider_call

        before = _get_counter(PROVIDER_CALLS, provider="higgsfield", operation="generate", status="error")
        record_provider_call("higgsfield", "generate", success=False)
        after = _get_counter(PROVIDER_CALLS, provider="higgsfield", operation="generate", status="error")
        assert after == before + 1

    def test_record_tool_call_success(self) -> None:
        from vos_studio_mcp.observability.metrics import MCP_TOOL_CALLS, record_tool_call

        before = _get_counter(MCP_TOOL_CALLS, tool="list_video_jobs", status="success")
        record_tool_call("list_video_jobs", success=True)
        after = _get_counter(MCP_TOOL_CALLS, tool="list_video_jobs", status="success")
        assert after == before + 1

    def test_update_circuit_breaker_gauges_reflects_open_state(self) -> None:
        from vos_studio_mcp.observability.metrics import (
            CIRCUIT_BREAKER_OPEN,
            update_circuit_breaker_gauges,
        )
        from vos_studio_mcp.services.circuit_breaker import CircuitBreaker

        breaker = CircuitBreaker("test_provider_metrics", failure_threshold=1, recovery_timeout=60.0)
        # Register it in the global registry by importing get_breaker
        from vos_studio_mcp.services.circuit_breaker import _registry
        _registry["test_provider_metrics"] = breaker

        # Initially closed
        update_circuit_breaker_gauges()
        assert CIRCUIT_BREAKER_OPEN.labels(provider="test_provider_metrics")._value.get() == 0

        # Open the breaker manually
        breaker._opened_at = __import__("time").monotonic()
        breaker._failures = 1

        update_circuit_breaker_gauges()
        assert CIRCUIT_BREAKER_OPEN.labels(provider="test_provider_metrics")._value.get() == 1

        # Cleanup
        del _registry["test_provider_metrics"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_counter(counter: object, **labels: str) -> float:  # type: ignore[type-arg]
    """Read the current value of a labelled Prometheus counter."""
    return counter.labels(**labels)._value.get()  # type: ignore[attr-defined]
