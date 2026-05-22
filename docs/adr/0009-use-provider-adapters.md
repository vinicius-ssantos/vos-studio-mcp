# ADR-0009 — Use provider adapters for Higgsfield, Freepik, and Magnific

Status: Amended  
Date: 2026-05-21  
Amended: 2026-05-22

## Context

The agency may use multiple creative providers. Each provider has different APIs, dashboards, MCP capabilities, billing rules, models, limits, and output formats.

Hardcoding provider logic inside MCP tools would make the codebase brittle.

## Decision

Create provider adapters behind a common internal interface. The interface contract is defined as a Python `typing.Protocol` (see ADR-0022 for the full specification).

All tool handlers access providers through a central registry (`providers/__init__.py`) keyed by `provider_id` string. No tool imports a concrete adapter class directly.

## Adapter implementation status

| Provider | `provider_id` | Status | Notes |
|----------|--------------|--------|-------|
| Manual dashboard | `manual_dashboard` | ✅ Implemented | `prepare_manual_pack` only; `generate_*` raises `NotImplementedError` |
| Higgsfield | `higgsfield` | ✅ Implemented | Video generation (text2video + image2video), job status, HMAC webhook verification, cost estimation |
| Freepik | `freepik` | ✅ Implemented | Image generation (text-to-image), async job status, HMAC webhook verification, cost estimation |
| Magnific | `magnific` | ✅ Implemented | Image upscaling (`generate_image` with `image_url`), async job status, HMAC webhook verification, cost estimation |

## Alternatives considered

- Hardcode provider calls inside each tool: fast but hard to maintain.
- Use one universal provider abstraction from day one: too abstract too early.
- Use thin provider adapters with shared conventions: accepted.

## Consequences

This improves maintainability and makes it easier to add or replace providers.

The tradeoff is a small upfront abstraction cost.

## Impact on VOS Studio MCP

- Tools call `get_adapter(provider_id)` from `src/vos_studio_mcp/services/providers/__init__.py`, not raw provider APIs directly.
- Each new adapter file lives in `src/vos_studio_mcp/services/providers/` and must satisfy the `ProviderAdapter` Protocol (ADR-0022) to pass `mypy` strict mode.
- API keys for each provider are configured via environment variables (ADR-0016): `HIGGSFIELD_API_KEY`, `FREEPIK_API_KEY`, `MAGNIFIC_API_KEY`.
