"""Unit tests for CorrelatedTask base class (ADR-0030)."""

from unittest.mock import MagicMock, patch

import pytest

from vos_studio_mcp.observability.context import request_id_var, trace_id_var
from vos_studio_mcp.tasks.base import CorrelatedTask


def _make_task(name: str = "test.task") -> CorrelatedTask:
    """Return a minimal CorrelatedTask instance wired to a mock app."""
    task = CorrelatedTask()
    task.name = name
    task.app = MagicMock()
    task.request_stack = MagicMock()
    task.request_stack.top = None
    return task


# ---------------------------------------------------------------------------
# apply_async — header injection
# ---------------------------------------------------------------------------


def test_apply_async_injects_trace_id() -> None:
    token = trace_id_var.set("trace-abc")
    try:
        task = _make_task()
        captured_headers: dict[str, str] = {}

        def capture_apply_async(self, args=None, kwargs=None, **options):  # type: ignore[misc]
            captured_headers.update(options.get("headers", {}))
            return MagicMock()

        with patch.object(CorrelatedTask.__bases__[0], "apply_async", capture_apply_async):
            task.apply_async()

        assert captured_headers.get("trace_id") == "trace-abc"
    finally:
        trace_id_var.reset(token)


def test_apply_async_injects_request_id() -> None:
    token = request_id_var.set("req-xyz")
    try:
        task = _make_task()
        captured_headers: dict[str, str] = {}

        def capture_apply_async(self, args=None, kwargs=None, **options):  # type: ignore[misc]
            captured_headers.update(options.get("headers", {}))
            return MagicMock()

        with patch.object(CorrelatedTask.__bases__[0], "apply_async", capture_apply_async):
            task.apply_async()

        assert captured_headers.get("request_id") == "req-xyz"
    finally:
        request_id_var.reset(token)


def test_apply_async_skips_none_values() -> None:
    """None context vars must not be added to headers."""
    task = _make_task()
    captured_headers: dict[str, str] = {}

    def capture_apply_async(self, args=None, kwargs=None, **options):  # type: ignore[misc]
        captured_headers.update(options.get("headers", {}))
        return MagicMock()

    with patch.object(CorrelatedTask.__bases__[0], "apply_async", capture_apply_async):
        task.apply_async()

    assert "trace_id" not in captured_headers
    assert "request_id" not in captured_headers


def test_apply_async_merges_with_existing_headers() -> None:
    token = trace_id_var.set("trace-merge")
    try:
        task = _make_task()
        captured_headers: dict[str, str] = {}

        def capture_apply_async(self, args=None, kwargs=None, **options):  # type: ignore[misc]
            captured_headers.update(options.get("headers", {}))
            return MagicMock()

        with patch.object(CorrelatedTask.__bases__[0], "apply_async", capture_apply_async):
            task.apply_async(headers={"custom_key": "custom_val"})

        assert captured_headers.get("trace_id") == "trace-merge"
        assert captured_headers.get("custom_key") == "custom_val"
    finally:
        trace_id_var.reset(token)


# ---------------------------------------------------------------------------
# __call__ — context restoration before task body runs
# ---------------------------------------------------------------------------


def test_call_sets_trace_id_from_headers() -> None:
    observed: list[str | None] = []

    class _TestTask(CorrelatedTask):
        abstract = False

        def run(self, *args, **kwargs):  # type: ignore[override]
            observed.append(trace_id_var.get())

    task = _TestTask()
    task.name = "test.trace"

    request = MagicMock()
    request.headers = {"trace_id": "trace-from-header"}
    task.request_stack = MagicMock()
    task.request_stack.top = request

    task.__call__()
    assert observed == ["trace-from-header"]


def test_call_sets_request_id_from_headers() -> None:
    observed: list[str | None] = []

    class _TestTask(CorrelatedTask):
        abstract = False

        def run(self, *args, **kwargs):  # type: ignore[override]
            observed.append(request_id_var.get())

    task = _TestTask()
    task.name = "test.request_id"

    request = MagicMock()
    request.headers = {"request_id": "req-from-header"}
    task.request_stack = MagicMock()
    task.request_stack.top = request

    task.__call__()
    assert observed == ["req-from-header"]


def test_call_restores_context_after_task_completes() -> None:
    outer_token = trace_id_var.set("outer-trace")
    try:
        class _TestTask(CorrelatedTask):
            abstract = False

            def run(self, *args, **kwargs):  # type: ignore[override]
                pass

        task = _TestTask()
        task.name = "test.restore"

        request = MagicMock()
        request.headers = {"trace_id": "inner-trace"}
        task.request_stack = MagicMock()
        task.request_stack.top = request

        task.__call__()

        # After task completes, outer context must be restored
        assert trace_id_var.get() == "outer-trace"
    finally:
        trace_id_var.reset(outer_token)


def test_call_restores_context_even_on_exception() -> None:
    outer_token = trace_id_var.set("outer-on-error")
    try:
        class _TestTask(CorrelatedTask):
            abstract = False

            def run(self, *args, **kwargs):  # type: ignore[override]
                raise RuntimeError("task failed")

        task = _TestTask()
        task.name = "test.restore-on-error"

        request = MagicMock()
        request.headers = {"trace_id": "inner-trace"}
        task.request_stack = MagicMock()
        task.request_stack.top = request

        with pytest.raises(RuntimeError):
            task.__call__()

        assert trace_id_var.get() == "outer-on-error"
    finally:
        trace_id_var.reset(outer_token)


def test_call_handles_missing_headers_gracefully() -> None:
    """Tasks with no headers (e.g. dispatched before migration) must not crash."""

    class _TestTask(CorrelatedTask):
        abstract = False

        def run(self, *args, **kwargs):  # type: ignore[override]
            pass

    task = _TestTask()
    task.name = "test.no-headers"

    request = MagicMock()
    request.headers = {}
    task.request_stack = MagicMock()
    task.request_stack.top = request

    task.__call__()  # must not raise
    assert trace_id_var.get() is None
    assert request_id_var.get() is None
