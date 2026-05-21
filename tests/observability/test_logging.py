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
