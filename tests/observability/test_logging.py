"""Tests for structured logging helpers."""

from vos_studio_mcp.observability.logging import redact_mapping


def test_redact_mapping_masks_sensitive_values() -> None:
    result = redact_mapping(
        {
            "provider_api_key": "secret",
            "client_id": "client_123",
            "authorization": "Bearer token",
        }
    )

    assert result["provider_api_key"] == "[REDACTED]"
    assert result["authorization"] == "[REDACTED]"
    assert result["client_id"] == "client_123"


# ---------------------------------------------------------------------------
# JsonFormatter
# ---------------------------------------------------------------------------


def test_json_formatter_basic_format() -> None:
    import json
    import logging

    from vos_studio_mcp.observability.logging import JsonFormatter

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello world",
        args=(),
        exc_info=None,
    )
    output = json.loads(formatter.format(record))
    assert output["level"] == "info"
    assert output["event"] == "hello world"
    assert output["logger"] == "test"
    assert "trace_id" in output
    assert "request_id" in output


def test_json_formatter_includes_trace_id() -> None:
    import json
    import logging

    from vos_studio_mcp.observability.context import trace_id_var
    from vos_studio_mcp.observability.logging import JsonFormatter

    token = trace_id_var.set("trace-abc-123")
    try:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="msg", args=(), exc_info=None,
        )
        output = json.loads(formatter.format(record))
        assert output["trace_id"] == "trace-abc-123"
    finally:
        trace_id_var.reset(token)


def test_json_formatter_redacts_sensitive_extra() -> None:
    import json
    import logging

    from vos_studio_mcp.observability.logging import JsonFormatter

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test", level=logging.WARNING, pathname="", lineno=0,
        msg="leak check", args=(), exc_info=None,
    )
    record.extra = {"api_key": "super-secret", "client_id": "c-123"}  # type: ignore[attr-defined]
    output = json.loads(formatter.format(record))
    assert output["api_key"] == "[REDACTED]"
    assert output["client_id"] == "c-123"


def test_json_formatter_includes_exception() -> None:
    import json
    import logging
    import sys

    from vos_studio_mcp.observability.logging import JsonFormatter

    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test", level=logging.ERROR, pathname="", lineno=0,
        msg="error", args=(), exc_info=exc_info,
    )
    output = json.loads(formatter.format(record))
    assert "exception" in output
    assert "ValueError" in output["exception"]


def test_configure_logging_sets_json_formatter() -> None:
    import logging

    from vos_studio_mcp.observability.logging import JsonFormatter, configure_logging

    root = logging.getLogger()
    # Save and restore root logger state so this test does not pollute others.
    original_handlers = root.handlers[:]
    original_level = root.level
    try:
        configure_logging("DEBUG")
        assert len(root.handlers) >= 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
        assert root.level == logging.DEBUG
    finally:
        root.handlers[:] = original_handlers
        root.setLevel(original_level)


# ---------------------------------------------------------------------------
# context.py — get_trace_id / get_request_id
# ---------------------------------------------------------------------------


def test_get_trace_id_returns_none_by_default() -> None:
    from vos_studio_mcp.observability.context import get_trace_id, trace_id_var

    token = trace_id_var.set(None)
    try:
        assert get_trace_id() is None
    finally:
        trace_id_var.reset(token)


def test_get_trace_id_returns_set_value() -> None:
    from vos_studio_mcp.observability.context import get_trace_id, trace_id_var

    token = trace_id_var.set("my-trace-id")
    try:
        assert get_trace_id() == "my-trace-id"
    finally:
        trace_id_var.reset(token)


def test_get_request_id_returns_none_by_default() -> None:
    from vos_studio_mcp.observability.context import get_request_id, request_id_var

    token = request_id_var.set(None)
    try:
        assert get_request_id() is None
    finally:
        request_id_var.reset(token)


def test_get_request_id_returns_set_value() -> None:
    from vos_studio_mcp.observability.context import get_request_id, request_id_var

    token = request_id_var.set("req-xyz")
    try:
        assert get_request_id() == "req-xyz"
    finally:
        request_id_var.reset(token)
