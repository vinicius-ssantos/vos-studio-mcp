"""Prometheus metrics definitions and collection helpers (Issue #30).

Metrics exposed at GET /metrics (Prometheus text format):

  vos_http_requests_total{method, path, status_code}    — request counter
  vos_http_request_duration_seconds{method, path}       — latency histogram
  vos_provider_calls_total{provider, operation, status} — provider API call counter
  vos_circuit_breaker_open{provider}                    — 1 if open, 0 otherwise
  vos_mcp_tool_calls_total{tool, status}                — MCP tool call counter

All metric names are prefixed with `vos_` to avoid collisions in shared clusters.
"""

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# ---------------------------------------------------------------------------
# HTTP request metrics
# ---------------------------------------------------------------------------

HTTP_REQUESTS = Counter(
    "vos_http_requests_total",
    "Total HTTP requests handled",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_DURATION = Histogram(
    "vos_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# ---------------------------------------------------------------------------
# Provider call metrics
# ---------------------------------------------------------------------------

PROVIDER_CALLS = Counter(
    "vos_provider_calls_total",
    "Total provider API calls",
    ["provider", "operation", "status"],
)

CIRCUIT_BREAKER_OPEN = Gauge(
    "vos_circuit_breaker_open",
    "1 if the circuit breaker is open (provider unavailable), 0 otherwise",
    ["provider"],
)

# ---------------------------------------------------------------------------
# MCP tool metrics
# ---------------------------------------------------------------------------

MCP_TOOL_CALLS = Counter(
    "vos_mcp_tool_calls_total",
    "Total MCP tool invocations",
    ["tool", "status"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def record_provider_call(provider: str, operation: str, *, success: bool) -> None:
    """Increment the provider call counter with success/error status."""
    PROVIDER_CALLS.labels(
        provider=provider,
        operation=operation,
        status="success" if success else "error",
    ).inc()


def record_tool_call(tool: str, *, success: bool) -> None:
    """Increment the MCP tool call counter."""
    MCP_TOOL_CALLS.labels(
        tool=tool,
        status="success" if success else "error",
    ).inc()


def update_circuit_breaker_gauges() -> None:
    """Refresh CIRCUIT_BREAKER_OPEN gauges from the live breaker registry.

    Called just before metrics are scraped so the values are always current.
    """
    from vos_studio_mcp.services.circuit_breaker import get_all_breakers

    for name, breaker in get_all_breakers().items():
        CIRCUIT_BREAKER_OPEN.labels(provider=name).set(
            1 if breaker.state == "open" else 0
        )


def metrics_response() -> tuple[bytes, str]:
    """Return (body_bytes, content_type) for the /metrics endpoint."""
    update_circuit_breaker_gauges()
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
