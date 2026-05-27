"""Higgsfield MCP client — Phase 1: discovery only (ADR-0044, Issue #73)."""

import json
import logging
from typing import Any

import httpx

from vos_studio_mcp.config.env import get_settings
from vos_studio_mcp.schemas.higgsfield_mcp import (
    HighgsfieldMcpCapabilitiesResponse,
    McpPromptInfo,
    McpResourceInfo,
    McpToolInfo,
)

log = logging.getLogger(__name__)

_PROTOCOL_VERSION = "2024-11-05"
_CLIENT_INFO = {"name": "vos-studio-mcp", "version": "1.0.0"}


def _auth_headers(token: str, session_id: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    return headers


def _rpc(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    rpc_id: int | None = None,
) -> dict[str, Any]:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if rpc_id is not None:
        msg["id"] = rpc_id
    if params is not None:
        msg["params"] = params
    return msg


def _extract_result(response: httpx.Response) -> dict[str, Any]:
    """Parse JSON-RPC result from a JSON or SSE response body."""
    ct = response.headers.get("content-type", "")
    if "text/event-stream" in ct:
        for line in response.text.splitlines():
            if line.startswith("data:"):
                data = line[5:].strip()
                if data and data != "[DONE]":
                    parsed: dict[str, Any] = json.loads(data)
                    return parsed
        return {}
    result: dict[str, Any] = response.json()
    return result


def _disabled() -> HighgsfieldMcpCapabilitiesResponse:
    return HighgsfieldMcpCapabilitiesResponse(
        status="disabled",
        tool_count=0,
        summary="Higgsfield MCP integration is disabled. Set HIGGSFIELD_MCP_ENABLED=true to activate.",
        next_action="configure_higgsfield_mcp",
    )


def _auth_required(reason: str) -> HighgsfieldMcpCapabilitiesResponse:
    return HighgsfieldMcpCapabilitiesResponse(
        status="auth_required",
        tool_count=0,
        summary=reason,
        next_action="set_higgsfield_mcp_access_token",
    )


def _unreachable(reason: str) -> HighgsfieldMcpCapabilitiesResponse:
    return HighgsfieldMcpCapabilitiesResponse(
        status="unreachable",
        tool_count=0,
        summary=reason,
        next_action="retry_later",
    )


async def list_higgsfield_mcp_capabilities() -> HighgsfieldMcpCapabilitiesResponse:
    """Perform an MCP handshake with the Higgsfield MCP server and list its capabilities."""
    settings = get_settings()

    if not settings.higgsfield_mcp_enabled:
        return _disabled()

    url = settings.higgsfield_mcp_url
    token = settings.higgsfield_mcp_access_token
    if not token:
        return _auth_required(
            "No Higgsfield MCP access token configured. Set HIGGSFIELD_MCP_ACCESS_TOKEN."
        )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Step 1: initialize handshake
            init_resp = await client.post(
                url,
                headers=_auth_headers(token),
                json=_rpc(
                    "initialize",
                    {
                        "protocolVersion": _PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": _CLIENT_INFO,
                    },
                    rpc_id=1,
                ),
            )

            if init_resp.status_code == 401:
                return _auth_required(
                    "Higgsfield MCP authentication failed. Verify HIGGSFIELD_MCP_ACCESS_TOKEN."
                )
            if not init_resp.is_success:
                log.warning(
                    "higgsfield_mcp.initialize.failed",
                    extra={"status": init_resp.status_code},
                )
                return _unreachable(
                    f"Higgsfield MCP server returned HTTP {init_resp.status_code} on initialize."
                )

            session_id: str | None = init_resp.headers.get("mcp-session-id")
            init_data = _extract_result(init_resp)
            rpc_result = init_data.get("result", {})
            server_info: dict[str, Any] = rpc_result.get("serverInfo", {})
            server_name: str | None = server_info.get("name")
            server_version: str | None = server_info.get("version")
            capabilities: dict[str, Any] = rpc_result.get("capabilities", {})

            # Step 2: spec-required initialized notification (no response expected)
            await client.post(
                url,
                headers=_auth_headers(token, session_id),
                json=_rpc("notifications/initialized"),
            )

            tools: list[McpToolInfo] = []
            resources: list[McpResourceInfo] = []
            prompts: list[McpPromptInfo] = []

            if "tools" in capabilities:
                resp = await client.post(
                    url,
                    headers=_auth_headers(token, session_id),
                    json=_rpc("tools/list", {}, rpc_id=2),
                )
                if resp.is_success:
                    items = _extract_result(resp).get("result", {}).get("tools", [])
                    tools = [
                        McpToolInfo(name=t.get("name", ""), description=t.get("description"))
                        for t in items
                    ]

            if "resources" in capabilities:
                resp = await client.post(
                    url,
                    headers=_auth_headers(token, session_id),
                    json=_rpc("resources/list", {}, rpc_id=3),
                )
                if resp.is_success:
                    items = _extract_result(resp).get("result", {}).get("resources", [])
                    resources = [
                        McpResourceInfo(
                            uri=r.get("uri", ""),
                            name=r.get("name"),
                            description=r.get("description"),
                        )
                        for r in items
                    ]

            if "prompts" in capabilities:
                resp = await client.post(
                    url,
                    headers=_auth_headers(token, session_id),
                    json=_rpc("prompts/list", {}, rpc_id=4),
                )
                if resp.is_success:
                    items = _extract_result(resp).get("result", {}).get("prompts", [])
                    prompts = [
                        McpPromptInfo(name=p.get("name", ""), description=p.get("description"))
                        for p in items
                    ]

        summary = (
            f"Connected to {server_name or 'Higgsfield MCP'} "
            f"v{server_version or 'unknown'}. "
            f"{len(tools)} tool(s), {len(resources)} resource(s), {len(prompts)} prompt(s)."
        )
        return HighgsfieldMcpCapabilitiesResponse(
            status="ok",
            server_name=server_name,
            server_version=server_version,
            tools=tools,
            resources=resources,
            prompts=prompts,
            tool_count=len(tools),
            summary=summary,
            next_action="request_api_video",
        )

    except httpx.ConnectError:
        log.warning("higgsfield_mcp.connect_error")
        return _unreachable(
            "Could not connect to Higgsfield MCP server. Check HIGGSFIELD_MCP_URL."
        )
    except httpx.TimeoutException:
        log.warning("higgsfield_mcp.timeout")
        return _unreachable("Higgsfield MCP server did not respond within timeout.")
    except Exception as exc:
        log.error("higgsfield_mcp.unexpected_error", extra={"error": str(exc)})
        return _unreachable("Unexpected error connecting to Higgsfield MCP server.")
