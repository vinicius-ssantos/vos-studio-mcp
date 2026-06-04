# Architecture Decision Records

This directory stores architecture decisions for the VOS Studio MCP project.

ADRs explain important decisions, the context behind them, alternatives considered, and consequences accepted.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-use-python-as-primary-language.md) | Use Python as the primary language | Amended |
| [0002](0002-build-remote-http-mcp-server.md) | Build a remote HTTP MCP server | Accepted |
| [0003](0003-separate-dashboard-manual-and-api-credits-modes.md) | Separate dashboard_manual and api_credits modes | Accepted |
| [0004](0004-do-not-automate-provider-dashboards.md) | Do not automate provider dashboards | Accepted |
| [0005](0005-require-human-approval-for-paid-or-external-actions.md) | Require human approval for paid or external actions | Amended |
| [0006](0006-use-workflow-oriented-tools-to-reduce-token-cost.md) | Use workflow-oriented tools to reduce token cost | Accepted |
| [0007](0007-use-supabase-postgres-as-system-of-record.md) | Use Supabase/Postgres as the system of record | Accepted |
| [0008](0008-store-assets-outside-the-mcp-and-return-references.md) | Store assets outside the MCP and return references | Accepted |
| [0009](0009-use-provider-adapters.md) | Use provider adapters for Higgsfield, Freepik, and Magnific | Accepted |
| [0010](0010-treat-creative-sprint-as-core-domain-entity.md) | Treat the Creative Sprint as the core domain entity | Accepted |
| [0011](0011-keep-mcp-tool-outputs-compact-and-structured.md) | Keep MCP tool outputs compact and structured | Accepted |
| [0012](0012-use-explicit-cost-budgets-and-generation-limits.md) | Use explicit cost budgets and generation limits | Accepted |
| [0013](0013-keep-prompts-and-presets-versioned.md) | Keep prompts and presets versioned | Accepted |
| [0014](0014-use-queues-for-long-running-generation-jobs.md) | Use queues for long-running generation jobs | Accepted |
| [0015](0015-implement-audit-logs-for-operational-traceability.md) | Implement audit logs for operational traceability | Accepted |
| [0016](0016-use-environment-variables-and-secret-management.md) | Use environment variables and secret management for credentials | Accepted |
| [0017](0017-start-private-first-and-client-safe-by-design.md) | Start private-first and client-safe by design | Accepted |
| [0018](0018-use-incremental-pr-based-development-with-coding-agents.md) | Use incremental PR-based development with coding agents | Accepted |
| [0019](0019-define-authentication-model-for-remote-mcp-server.md) | Define authentication model for the remote MCP server | Accepted |
| [0020](0020-database-schema-evolution-and-migration-strategy.md) | Database schema evolution and migration strategy | Accepted |
| [0021](0021-job-queue-technology-selection.md) | Job queue technology selection | Amended |
| [0022](0022-provider-adapter-interface-contract.md) | Provider adapter interface contract | Amended |
| [0023](0023-multitenancy-and-client-data-isolation.md) | Multitenancy and client data isolation | Accepted |
| [0024](0024-brand-kit-entity-specification.md) | Brand kit entity specification | Accepted |
| [0025](0025-performance-feedback-loop-and-creative-learning.md) | Performance feedback loop and creative learning | Accepted |
| [0026](0026-testing-strategy.md) | Testing strategy | Accepted |
| [0027](0027-ab-testing-within-creative-sprints.md) | A/B testing within creative sprints | Accepted |
| [0028](0028-provider-webhook-support.md) | Provider webhook support | Accepted |
| [0029](0029-cross-client-prompt-library.md) | Cross-client prompt library | Accepted |
| [0030](0030-observability-and-failure-diagnostics.md) | Observability and failure diagnostics | Accepted |
| [0031](0031-split-generation-storage-status.md) | Split generation_status from storage_status | Accepted |
| [0032](0032-ssrf-protection-for-outbound-webhooks.md) | SSRF protection for outbound webhook delivery | Accepted |
| [0033](0033-cross-tenant-authorization-regression-matrix.md) | Cross-tenant authorization regression matrix | Accepted |
| [0034](0034-provider-usage-ledger.md) | Provider usage ledger and global daily quota | Accepted |
| [0035](0035-circuit-breaker-for-provider-resilience.md) | Circuit breaker for provider resilience | Accepted |
| [0036](0036-outbound-webhook-retry-policy.md) | Outbound webhook retry policy | Accepted |
| [0037](0037-asset-stage-and-lineage-model.md) | Asset stage and lineage model | Accepted |
| [0038](0038-brand-kit-asset-lock-v2.md) | BrandKit Asset Lock (campaign visual system v2) | Accepted |
| [0039](0039-vos-native-domain-evolution-roadmap.md) | Evolve the architecture toward a VOS-native creative domain | Proposed |
| [0040](0040-rls-enforcement-role-model-and-ssrf-ip-pinning.md) | RLS enforcement role model and outbound SSRF IP pinning | Proposed |
| [0044](0044-vos-as-mcp-client-for-provider-mcp-servers.md) | VOS as MCP client for provider MCP servers | Accepted |
