"""Read-only diagnostics for the MCP tool catalog exposed by FastMCP."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from typing import Any, TypedDict, cast

from vos_studio_mcp.schemas.status import ToolSchemaProbeResponse

_COMMIT_ENV_VARS = (
    "RAILWAY_GIT_COMMIT_SHA",
    "RAILWAY_GIT_COMMIT",
    "RENDER_GIT_COMMIT",
    "GIT_COMMIT",
    "SOURCE_VERSION",
)


class ToolCatalogSnapshot(TypedDict):
    catalog_fingerprint: str
    registered_tools_count: int
    tool_names: list[str]


def get_commit_sha() -> str:
    """Return the deployment commit SHA when the host exposes it."""
    for key in _COMMIT_ENV_VARS:
        value = os.getenv(key)
        if value:
            return value
    return "unknown"


def registered_tools(mcp: object) -> list[Any]:
    """Return the tools registered in FastMCP without depending on private types."""
    manager = getattr(mcp, "_tool_manager", None)
    list_tools = getattr(manager, "list_tools", None)
    if not callable(list_tools):
        return []
    try:
        tools = list_tools()
    except Exception:
        return []
    return list(tools or [])


def compute_tool_schema_version(tools: Iterable[Any]) -> str:
    """Compute a stable short hash for the advertised tool schemas."""
    payload = [_tool_fingerprint(tool) for tool in tools]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def tool_catalog_snapshot(tools: Iterable[Any]) -> ToolCatalogSnapshot:
    """Return compact catalog identity metadata."""
    tool_list = list(tools)
    names = sorted(_tool_name(tool) for tool in tool_list)
    raw = json.dumps(names, sort_keys=True, separators=(",", ":"))
    return {
        "catalog_fingerprint": hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12],
        "registered_tools_count": len(tool_list),
        "tool_names": names,
    }


def build_tool_schema_probe(tools: Iterable[Any], tool_name: str) -> ToolSchemaProbeResponse:
    """Inspect one registered tool schema as the MCP client sees it."""
    tool_list = list(tools)
    schema_version = compute_tool_schema_version(tool_list)
    snapshot = tool_catalog_snapshot(tool_list)
    target = next((tool for tool in tool_list if _tool_name(tool) == tool_name), None)

    if target is None:
        return ToolSchemaProbeResponse(
            tool_name=tool_name,
            server_registered=False,
            tool_schema_version=schema_version,
            catalog_fingerprint=str(snapshot["catalog_fingerprint"]),
            registered_tools_count=snapshot["registered_tools_count"],
            advice="tool_not_registered_or_reconnect_required",
        )

    schema = _extract_schema(target)
    required = sorted(_collect_required_fields(schema))
    properties = sorted(_collect_property_names(schema))

    return ToolSchemaProbeResponse(
        tool_name=tool_name,
        server_registered=True,
        tool_schema_version=schema_version,
        catalog_fingerprint=str(snapshot["catalog_fingerprint"]),
        registered_tools_count=snapshot["registered_tools_count"],
        required=required,
        input_properties=properties,
        uri_supported="uri" in properties,
        mime_type_supported="mime_type" in properties,
        storage_url_required=_is_field_required(schema, "storage_url"),
        advice="ok",
    )


def _tool_name(tool: Any) -> str:
    return str(getattr(tool, "name", None) or getattr(tool, "__name__", "unknown"))


def _tool_fingerprint(tool: Any) -> dict[str, object]:
    return {
        "name": _tool_name(tool),
        "description": getattr(tool, "description", None),
        "input_schema": _extract_schema(tool),
    }


def _extract_schema(tool: Any) -> dict[str, Any]:
    for attr in ("input_schema", "inputSchema", "parameters"):
        value = getattr(tool, attr, None)
        if isinstance(value, Mapping):
            return cast(dict[str, Any], _jsonable(value))

    fn_metadata = getattr(tool, "fn_metadata", None)
    arg_model = getattr(fn_metadata, "arg_model", None)
    model_json_schema = getattr(arg_model, "model_json_schema", None)
    if callable(model_json_schema):
        raw = model_json_schema()
        if isinstance(raw, Mapping):
            return cast(dict[str, Any], _jsonable(raw))

    return {}


def _jsonable(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, sort_keys=True, default=str))
    except TypeError:
        return str(value)


def _collect_property_names(schema: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(schema, Mapping):
        properties = schema.get("properties")
        if isinstance(properties, Mapping):
            names.update(str(name) for name in properties)
        for value in schema.values():
            names.update(_collect_property_names(value))
    elif isinstance(schema, list):
        for item in schema:
            names.update(_collect_property_names(item))
    return names


def _collect_required_fields(schema: Any) -> set[str]:
    required: set[str] = set()
    if isinstance(schema, Mapping):
        value = schema.get("required")
        if isinstance(value, list):
            required.update(str(name) for name in value)
        for child in schema.values():
            required.update(_collect_required_fields(child))
    elif isinstance(schema, list):
        for item in schema:
            required.update(_collect_required_fields(item))
    return required


def _is_field_required(schema: Any, field_name: str) -> bool:
    if isinstance(schema, Mapping):
        properties = schema.get("properties")
        required = schema.get("required")
        if isinstance(properties, Mapping) and field_name in properties:
            return isinstance(required, list) and field_name in required
        return any(_is_field_required(child, field_name) for child in schema.values())
    if isinstance(schema, list):
        return any(_is_field_required(item, field_name) for item in schema)
    return False
