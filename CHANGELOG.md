# Changelog

## [Unreleased]

### Added

- MCP tool schema diagnostics via `tool_schema_probe`, including catalog fingerprint,
  schema version, registered tool count, and alias support checks for MCP clients.
- `get_server_status` now reports deployment commit and MCP tool catalog identity
  metadata so clients can verify whether they are seeing the current tool surface.

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Releases from `v0.2.0` onwards are generated automatically by
[python-semantic-release](https://python-semantic-release.readthedocs.io/)
from [Conventional Commits](https://www.conventionalcommits.org/).

---

## [0.1.0] — 2026-05-24

Initial release of VOS Studio MCP — creative operations server for AI-assisted agency workflows.

### Features

- **18 MCP tools** covering the full creative lifecycle:
  - `create_client`, `save_brand_kit`
  - `create_creative_sprint`, `get_sprint_status`, `close_sprint`
  - `prepare_video_blueprint`, `request_api_video`, `get_video_job_status`
  - `list_sprint_assets`, `register_manual_asset`, `promote_to_library`
  - `record_asset_performance`, `record_performance_metrics`
  - `conclude_variant_test`, `prepare_dashboard_pack`
  - `get_server_status`
- **Provider adapters**: Higgsfield (video), Freepik (image), Magnific (upscale), Manual Dashboard
- **Celery worker** for async video polling and upload tasks
- **OAuth 2.1 auth middleware** with Supabase JWT and dev-bypass support
- **RLS isolation** — every DB query is scoped to `client_id` via Postgres session variables
- **Performance feedback loop** — `PerformanceRecord` table + `performance_context` in sprint creation
- **A/B variant testing** — `VariantGroup` / `VariantResult` models with `conclude_variant_test`
- **Prompt library** — cross-client asset promotion with `promote_to_library`
- **Audit log** — every tool call emits a structured `audit_event`
- **Sentry + structured logging** — `trace_id` on every request
- **Detailed `/health` endpoint** — concurrent checks for database, Redis and Celery worker
- **Deploy infra**: multi-stage Dockerfile, docker-compose, Railway and Render configs

### Architecture

31 Architecture Decision Records (ADRs 0001–0031) covering database isolation,
provider contracts, auth, observability, storage, cost controls, and more.

[0.1.0]: https://github.com/vinicius-ssantos/vos-studio-mcp/releases/tag/v0.1.0
