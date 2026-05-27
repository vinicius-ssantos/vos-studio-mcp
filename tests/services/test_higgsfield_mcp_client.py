"""Unit tests for Higgsfield MCP client — Phase 1 discovery (ADR-0044)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

_SERVICE = "vos_studio_mcp.services.mcp_clients.higgsfield"
_SETTINGS = f"{_SERVICE}.get_settings"


def _settings(
    *,
    enabled: bool = True,
    url: str = "https://mcp.higgsfield.ai/mcp",
    token: str = "test-token",
) -> MagicMock:
    s = MagicMock()
    s.higgsfield_mcp_enabled = enabled
    s.higgsfield_mcp_url = url
    s.higgsfield_mcp_access_token = token
    return s


def _http_response(
    status_code: int = 200,
    json_body: dict | None = None,
    headers: dict | None = None,
) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.headers = headers or {}
    resp.json = MagicMock(return_value=json_body or {})
    resp.text = ""
    return resp


def _init_response(
    server_name: str = "higgsfield-mcp",
    server_version: str = "1.0.0",
    capabilities: dict | None = None,
    session_id: str | None = None,
) -> MagicMock:
    headers: dict[str, str] = {}
    if session_id:
        headers["mcp-session-id"] = session_id
    caps = capabilities if capabilities is not None else {"tools": {}}
    return _http_response(
        json_body={
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": server_name, "version": server_version},
                "capabilities": caps,
            },
        },
        headers=headers,
    )


def _tools_response(tools: list[dict] | None = None) -> MagicMock:
    return _http_response(
        json_body={
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"tools": tools or []},
        }
    )


def _mock_client(*responses: MagicMock) -> tuple[MagicMock, MagicMock]:
    """Return (mock_AsyncClient_class, mock_client_instance)."""
    client = AsyncMock()
    client.post = AsyncMock(side_effect=list(responses))

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    cls = MagicMock(return_value=ctx)
    return cls, client


# ---------------------------------------------------------------------------
# Disabled / missing config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_returns_disabled_status() -> None:
    from vos_studio_mcp.services.mcp_clients.higgsfield import list_higgsfield_mcp_capabilities

    with patch(_SETTINGS, return_value=_settings(enabled=False)):
        result = await list_higgsfield_mcp_capabilities()

    assert result.status == "disabled"
    assert result.tool_count == 0
    assert "HIGGSFIELD_MCP_ENABLED" in result.summary


@pytest.mark.asyncio
async def test_missing_token_returns_auth_required() -> None:
    from vos_studio_mcp.services.mcp_clients.higgsfield import list_higgsfield_mcp_capabilities

    with patch(_SETTINGS, return_value=_settings(token="")):
        result = await list_higgsfield_mcp_capabilities()

    assert result.status == "auth_required"
    assert result.tool_count == 0
    assert "HIGGSFIELD_MCP_ACCESS_TOKEN" in result.summary


# ---------------------------------------------------------------------------
# Auth failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_401_returns_auth_required() -> None:
    from vos_studio_mcp.services.mcp_clients.higgsfield import list_higgsfield_mcp_capabilities

    cls, _ = _mock_client(_http_response(status_code=401))
    with patch(_SETTINGS, return_value=_settings()), patch(f"{_SERVICE}.httpx.AsyncClient", cls):
        result = await list_higgsfield_mcp_capabilities()

    assert result.status == "auth_required"
    assert "authentication failed" in result.summary.lower()


# ---------------------------------------------------------------------------
# Server errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_500_returns_unreachable() -> None:
    from vos_studio_mcp.services.mcp_clients.higgsfield import list_higgsfield_mcp_capabilities

    cls, _ = _mock_client(_http_response(status_code=500))
    with patch(_SETTINGS, return_value=_settings()), patch(f"{_SERVICE}.httpx.AsyncClient", cls):
        result = await list_higgsfield_mcp_capabilities()

    assert result.status == "unreachable"
    assert "500" in result.summary


@pytest.mark.asyncio
async def test_connect_error_returns_unreachable() -> None:
    from vos_studio_mcp.services.mcp_clients.higgsfield import list_higgsfield_mcp_capabilities

    client = AsyncMock()
    client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(_SETTINGS, return_value=_settings()), patch(
        f"{_SERVICE}.httpx.AsyncClient", return_value=ctx
    ):
        result = await list_higgsfield_mcp_capabilities()

    assert result.status == "unreachable"
    assert "connect" in result.summary.lower()


@pytest.mark.asyncio
async def test_timeout_returns_unreachable() -> None:
    from vos_studio_mcp.services.mcp_clients.higgsfield import list_higgsfield_mcp_capabilities

    client = AsyncMock()
    client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch(_SETTINGS, return_value=_settings()), patch(
        f"{_SERVICE}.httpx.AsyncClient", return_value=ctx
    ):
        result = await list_higgsfield_mcp_capabilities()

    assert result.status == "unreachable"
    assert "timeout" in result.summary.lower()


# ---------------------------------------------------------------------------
# Successful handshake
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_handshake_returns_ok() -> None:
    from vos_studio_mcp.services.mcp_clients.higgsfield import list_higgsfield_mcp_capabilities

    tool_list = [
        {"name": "generate_video", "description": "Generate a video"},
        {"name": "show_generations", "description": "List recent generations"},
    ]
    # Responses: initialize, notifications/initialized, tools/list
    cls, _ = _mock_client(
        _init_response(capabilities={"tools": {}}),
        _http_response(status_code=200),  # notifications/initialized
        _tools_response(tool_list),
    )

    with patch(_SETTINGS, return_value=_settings()), patch(f"{_SERVICE}.httpx.AsyncClient", cls):
        result = await list_higgsfield_mcp_capabilities()

    assert result.status == "ok"
    assert result.server_name == "higgsfield-mcp"
    assert result.server_version == "1.0.0"
    assert result.tool_count == 2
    assert len(result.tools) == 2
    assert result.tools[0].name == "generate_video"


@pytest.mark.asyncio
async def test_no_capabilities_returns_ok_with_empty_lists() -> None:
    from vos_studio_mcp.services.mcp_clients.higgsfield import list_higgsfield_mcp_capabilities

    # Server reports no tools/resources/prompts capabilities
    cls, _ = _mock_client(
        _init_response(capabilities={}),
        _http_response(status_code=200),  # notifications/initialized
    )

    with patch(_SETTINGS, return_value=_settings()), patch(f"{_SERVICE}.httpx.AsyncClient", cls):
        result = await list_higgsfield_mcp_capabilities()

    assert result.status == "ok"
    assert result.tool_count == 0
    assert result.tools == []
    assert result.resources == []
    assert result.prompts == []


@pytest.mark.asyncio
async def test_session_id_forwarded_in_subsequent_requests() -> None:
    from vos_studio_mcp.services.mcp_clients.higgsfield import list_higgsfield_mcp_capabilities

    cls, mock_client = _mock_client(
        _init_response(capabilities={"tools": {}}, session_id="sess-abc"),
        _http_response(status_code=200),
        _tools_response(),
    )

    with patch(_SETTINGS, return_value=_settings()), patch(f"{_SERVICE}.httpx.AsyncClient", cls):
        await list_higgsfield_mcp_capabilities()

    # Second and third post calls should carry the session id header
    calls = mock_client.post.call_args_list
    assert len(calls) == 3
    _, kwargs2 = calls[1]
    assert kwargs2.get("headers", {}).get("Mcp-Session-Id") == "sess-abc"


@pytest.mark.asyncio
async def test_sse_response_parsed_correctly() -> None:
    from vos_studio_mcp.services.mcp_clients.higgsfield import list_higgsfield_mcp_capabilities

    sse_body = (
        'data: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",'
        '"serverInfo":{"name":"hf","version":"2"},"capabilities":{"tools":{}}}}\n\n'
    )
    init_resp = MagicMock(spec=httpx.Response)
    init_resp.status_code = 200
    init_resp.is_success = True
    init_resp.headers = {"content-type": "text/event-stream"}
    init_resp.text = sse_body
    init_resp.json = MagicMock(side_effect=Exception("should not be called"))

    cls, _ = _mock_client(
        init_resp,
        _http_response(status_code=200),
        _tools_response(),
    )

    with patch(_SETTINGS, return_value=_settings()), patch(f"{_SERVICE}.httpx.AsyncClient", cls):
        result = await list_higgsfield_mcp_capabilities()

    assert result.status == "ok"
    assert result.server_name == "hf"
    assert result.server_version == "2"
