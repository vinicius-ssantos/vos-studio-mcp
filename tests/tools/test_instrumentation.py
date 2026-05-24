"""Unit tests for the @instrument decorator (_instrumentation.py)."""

from unittest.mock import patch

import pytest

_MODULE = "vos_studio_mcp.tools._instrumentation"
_RECORD_TOOL_CALL = "vos_studio_mcp.observability.metrics.record_tool_call"


# ---------------------------------------------------------------------------
# Happy path: success is recorded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_instrument_records_success() -> None:
    from vos_studio_mcp.tools._instrumentation import instrument

    @instrument
    async def my_tool() -> str:
        return "ok"

    with patch(f"{_MODULE}._record") as mock_record:
        result = await my_tool()

    assert result == "ok"
    mock_record.assert_called_once_with("my_tool", success=True)


# ---------------------------------------------------------------------------
# Error path: exception is recorded and re-raised
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_instrument_records_failure_and_reraises() -> None:
    """When the wrapped tool raises, the exception must propagate and be recorded."""
    from vos_studio_mcp.tools._instrumentation import instrument

    @instrument
    async def bad_tool() -> None:
        raise ValueError("intentional failure")

    with patch(f"{_MODULE}._record") as mock_record:  # noqa: SIM117
        with pytest.raises(ValueError, match="intentional failure"):
            await bad_tool()

    mock_record.assert_called_once_with("bad_tool", success=False)


@pytest.mark.asyncio
async def test_instrument_preserves_tool_name() -> None:
    """The tool_name passed to _record must match the original function name."""
    from vos_studio_mcp.tools._instrumentation import instrument

    @instrument
    async def specific_tool_name() -> None:
        raise RuntimeError("boom")

    with patch(f"{_MODULE}._record") as mock_record, pytest.raises(RuntimeError):
        await specific_tool_name()

    name_used = mock_record.call_args.args[0]
    assert name_used == "specific_tool_name"


# ---------------------------------------------------------------------------
# _record: metrics failures are silenced
# ---------------------------------------------------------------------------


def test_record_silences_import_error() -> None:
    """If record_tool_call raises (e.g. missing metrics module), _record must not propagate."""
    from vos_studio_mcp.tools._instrumentation import _record

    # Patch the metrics function itself to raise, then verify _record swallows it
    with patch(
        "vos_studio_mcp.observability.metrics.record_tool_call",
        side_effect=RuntimeError("prometheus broken"),
    ):
        _record("any_tool", success=True)  # must not raise


def test_record_silences_attribute_error() -> None:
    """_record must swallow AttributeError if metrics aren't initialised yet."""
    from vos_studio_mcp.tools._instrumentation import _record

    with patch(
        "vos_studio_mcp.observability.metrics.record_tool_call",
        side_effect=AttributeError("counter not ready"),
    ):
        _record("any_tool", success=False)  # must not raise
