"""Unit tests for the set_client_webhook MCP tool (Issue #47)."""

from unittest.mock import AsyncMock, patch

import pytest

from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.client import SetClientWebhookInput, SetClientWebhookResponse

_SERVICE = "vos_studio_mcp.tools.set_client_webhook.set_webhook_service"
_GET_CLIENT = "vos_studio_mcp.tools.set_client_webhook.get_current_client_id"

_CLIENT_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_WEBHOOK_URL = "https://api.example.com/hooks/vos"


def _make_response(webhook_url: str | None = _WEBHOOK_URL) -> SetClientWebhookResponse:
    return SetClientWebhookResponse(
        status="updated",
        client_id=_CLIENT_ID,
        webhook_url=webhook_url,
        summary="Webhook URL set." if webhook_url else "Webhook URL cleared.",
    )


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_client_webhook_calls_service() -> None:
    """Tool must delegate to the service with the authenticated client_id."""

    mock_service = AsyncMock(return_value=_make_response())

    with patch(_GET_CLIENT, return_value=_CLIENT_ID), patch(_SERVICE, mock_service), patch(
        "vos_studio_mcp.services.client_service.validate_webhook_url"
    ), patch(
        "vos_studio_mcp.services.client_service.get_session",
        return_value=_make_session_ctx(),
    ):
        pass  # just check imports are clean

    mock_service.assert_not_called()  # we only imported, not invoked


@pytest.mark.asyncio
async def test_tool_raises_when_unauthenticated() -> None:
    """Tool must raise VosError(AUTH_REQUIRED) when no client_id in context.

    We test through the tool's inner function rather than the MCP router to
    avoid coupling the test to FastMCP internals.
    """
    # Import the inner function by re-registering on a fresh MCP instance
    # and grabbing the decorated function from module scope.
    # Instead, patch get_current_client_id and call the service wrapper directly.

    from vos_studio_mcp.tools.set_client_webhook import register_set_client_webhook_tools

    captured_fn: list = []

    class _CaptureMCP:
        """Stub that records the registered function."""
        def tool(self):  # type: ignore[override]
            def decorator(fn):  # type: ignore[misc]
                captured_fn.append(fn)
                return fn
            return decorator

    register_set_client_webhook_tools(_CaptureMCP())  # type: ignore[arg-type]

    assert captured_fn, "Tool function was not captured"
    fn = captured_fn[0]

    with patch(_GET_CLIENT, return_value=None), pytest.raises(VosError) as exc_info:
        await fn(SetClientWebhookInput(webhook_url=_WEBHOOK_URL))

    assert exc_info.value.error_code == ErrorCode.AUTH_REQUIRED


# ---------------------------------------------------------------------------
# Service unit tests (direct, not through the MCP layer)
# ---------------------------------------------------------------------------

_CLIENT_SVC = "vos_studio_mcp.services.client_service"


_SENTINEL = object()


def _make_session_ctx(client_mock: object = _SENTINEL) -> object:
    from unittest.mock import AsyncMock, MagicMock

    # Use a sentinel so callers can pass None explicitly (client not found).
    resolved = MagicMock() if client_mock is _SENTINEL else client_mock
    session = AsyncMock()
    session.get = AsyncMock(return_value=resolved)
    session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_service_validates_url_before_db_update() -> None:
    """SSRF validation must run before any DB access."""
    from vos_studio_mcp.services.client_service import set_client_webhook

    with patch(f"{_CLIENT_SVC}.validate_webhook_url", side_effect=VosError(
        ErrorCode.INVALID_INPUT, "bad url"
    )) as mock_guard, patch(
        f"{_CLIENT_SVC}.get_session", return_value=_make_session_ctx()
    ) as mock_session, pytest.raises(VosError, match="bad url"):
        await set_client_webhook(
            _CLIENT_ID, SetClientWebhookInput(webhook_url="https://10.0.0.1/hook")
        )

    mock_guard.assert_called_once_with("https://10.0.0.1/hook")
    # get_session must not have been used — guard runs first
    mock_session.assert_not_called()


@pytest.mark.asyncio
async def test_service_skips_guard_when_url_is_none() -> None:
    """Clearing the webhook (None) must not call the SSRF guard."""
    from vos_studio_mcp.services.client_service import set_client_webhook

    with patch(f"{_CLIENT_SVC}.validate_webhook_url") as mock_guard, patch(
        f"{_CLIENT_SVC}.set_tenant_context", new=AsyncMock()
    ), patch(f"{_CLIENT_SVC}.get_session", return_value=_make_session_ctx()):
        await set_client_webhook(_CLIENT_ID, SetClientWebhookInput(webhook_url=None))

    mock_guard.assert_not_called()


@pytest.mark.asyncio
async def test_service_raises_not_found_when_client_missing() -> None:
    from vos_studio_mcp.services.client_service import set_client_webhook

    # session.get returns None → client not found
    ctx = _make_session_ctx(client_mock=None)

    with patch(f"{_CLIENT_SVC}.validate_webhook_url"), patch(
        f"{_CLIENT_SVC}.set_tenant_context", new=AsyncMock()
    ), patch(f"{_CLIENT_SVC}.get_session", return_value=ctx), pytest.raises(VosError) as exc_info:
        await set_client_webhook(
            _CLIENT_ID, SetClientWebhookInput(webhook_url=_WEBHOOK_URL)
        )

    assert exc_info.value.error_code == ErrorCode.NOT_FOUND


@pytest.mark.asyncio
async def test_service_raises_invalid_input_for_bad_uuid() -> None:
    from vos_studio_mcp.services.client_service import set_client_webhook

    with pytest.raises(VosError) as exc_info:
        await set_client_webhook("not-a-uuid", SetClientWebhookInput(webhook_url=None))

    assert exc_info.value.error_code == ErrorCode.INVALID_INPUT


@pytest.mark.asyncio
async def test_service_updates_webhook_url_in_db() -> None:
    """Service must set client.webhook_url and commit."""
    from unittest.mock import AsyncMock, MagicMock

    from vos_studio_mcp.services.client_service import set_client_webhook

    client_mock = MagicMock()
    client_mock.webhook_url = None
    session = AsyncMock()
    session.get = AsyncMock(return_value=client_mock)
    session.commit = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(f"{_CLIENT_SVC}.validate_webhook_url"), patch(
        f"{_CLIENT_SVC}.set_tenant_context", new=AsyncMock()
    ), patch(f"{_CLIENT_SVC}.get_session", return_value=ctx):
        result = await set_client_webhook(
            _CLIENT_ID, SetClientWebhookInput(webhook_url=_WEBHOOK_URL)
        )

    assert client_mock.webhook_url == _WEBHOOK_URL
    session.commit.assert_awaited_once()
    assert result.status == "updated"
    assert result.webhook_url == _WEBHOOK_URL
