"""Tests for MCP tool catalog diagnostics."""

from types import SimpleNamespace

from vos_studio_mcp.services.tool_catalog_service import (
    build_tool_schema_probe,
    compute_tool_schema_version,
    tool_catalog_snapshot,
)


def test_tool_catalog_snapshot_returns_stable_identity() -> None:
    tools = [
        SimpleNamespace(name="beta", input_schema={"type": "object"}),
        SimpleNamespace(name="alpha", input_schema={"type": "object"}),
    ]

    first = tool_catalog_snapshot(tools)
    second = tool_catalog_snapshot(reversed(tools))

    assert first["registered_tools_count"] == 2
    assert first["tool_names"] == ["alpha", "beta"]
    assert first["catalog_fingerprint"] == second["catalog_fingerprint"]


def test_compute_tool_schema_version_changes_when_schema_changes() -> None:
    base = [SimpleNamespace(name="register_manual_asset", input_schema={"properties": {"uri": {}}})]
    changed = [
        SimpleNamespace(
            name="register_manual_asset",
            input_schema={"properties": {"uri": {}, "mime_type": {}}},
        )
    ]

    assert compute_tool_schema_version(base) != compute_tool_schema_version(changed)


def test_tool_schema_probe_detects_nested_asset_aliases() -> None:
    tool = SimpleNamespace(
        name="register_manual_asset",
        input_schema={
            "type": "object",
            "required": ["data"],
            "properties": {"data": {"$ref": "#/$defs/AssetInput"}},
            "$defs": {
                "AssetInput": {
                    "type": "object",
                    "required": ["sprint_id", "provider"],
                    "properties": {
                        "sprint_id": {"type": "string"},
                        "provider": {"type": "string"},
                        "storage_url": {"type": "string"},
                        "uri": {"type": "string"},
                        "format": {"type": "string"},
                        "mime_type": {"type": "string"},
                    },
                }
            },
        },
    )

    result = build_tool_schema_probe([tool], "register_manual_asset")

    assert result.server_registered is True
    assert result.uri_supported is True
    assert result.mime_type_supported is True
    assert result.storage_url_required is False
    assert "storage_url" in result.input_properties
    assert result.advice == "ok"


def test_tool_schema_probe_reports_missing_tool() -> None:
    result = build_tool_schema_probe([], "register_manual_asset")

    assert result.server_registered is False
    assert result.advice == "tool_not_registered_or_reconnect_required"
