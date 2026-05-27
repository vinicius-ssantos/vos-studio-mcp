# VOS Studio MCP

VOS Studio MCP is the operational Model Context Protocol server for **VOS Studio**, a performance creative studio focused on AI-assisted creative production for ads, product launches, and e-commerce campaigns.

This project acts as the internal creative operations layer that connects briefs, brand kits, creative strategy, prompt packs, generation providers, asset QA, cost controls, approvals, and delivery workflows.

The goal is not to build a generic AI image/video generator. The goal is to build a structured creative production system for a real agency workflow.

---

## Vision

VOS Studio MCP should act as the agency's creative operating system.

It should help turn a client brief into a repeatable, trackable creative sprint:

```text
client briefing
  → brand kit
  → creative angles
  → hooks
  → prompt packs
  → stage-aware execution pack or API generation job
  → asset registration
  → quality review
  → final delivery
```

The system should make creative production faster, more consistent, easier to audit, and safer to operate with AI tools.

---

## Vocabulary conventions

To keep the business language and the implementation language aligned, this repository uses the following conventions:

- **Business stage names**: Stage 0, Stage A, Stage B, Stage C, Repair, Final
- **Internal stage identifiers**: `stage_0`, `stage_a`, `stage_b`, `stage_c`, `repair`, `final`
- **Asset Lock**: the campaign visual system / constraint layer used by VOS; the persisted field name is `asset_lock`
- **Operating modes**: use the exact internal mode names `dashboard_manual` and `api_credits`
- **Delivery readiness**: business readiness for a downstream step or final handoff; this is distinct from provider generation completion and distinct from storage upload completion

In other words:
- "generation completed" does not always mean "stored"
- "stored" does not always mean "delivery-ready"
- "Final" is the business stage for the delivery asset, not just a storage state

---

## What this server is responsible for

The MCP server is responsible for orchestrating the creative workflow, not for replacing every creative or production decision.

It manages:

- clients
- brand kits
- creative briefs
- creative sprints
- campaign angles
- prompt packs and provider settings
- stage-aware execution packs
- API/credit-based generation jobs
- manual asset registration
- stage-aware asset metadata
- creative QA and repair routing
- approval checkpoints
- delivery assets
- cost estimation and budget limits
- provider usage summaries
- audit logs
- performance feedback loops

---

## What this server is not

This project is not intended to be:

- a dashboard automation bot
- a scraping tool
- a browser automation layer for provider websites
- a way to bypass provider usage limits
- a replacement for official provider APIs, MCP servers, or CLIs
- a place to store raw client assets directly in the Git repository
- a place to commit credentials, cookies, tokens, or API keys

Provider dashboards such as Freepik, Higgsfield, and Magnific must not be automated through logged-in browser sessions, Playwright, Selenium, scraping, or simulated human clicks.

The MCP can prepare instructions, prompts, presets, and checklists for a human operator. Automated execution should only happen through official and permitted APIs, MCP servers, or CLIs.

---

## Current architecture and maturity

The project is no longer just a foundation skeleton. It now includes a more explicit **VOS-native** domain model and operational workflow, including:

- stage-aware assets with lineage and delivery/reference semantics
- BrandKit Asset Lock / campaign visual system support
- VOS 9-shot blueprint generation
- stage-aware execution packs for Stage 0 / A / B / C / Repair / Final
- API-driven video generation with async polling and storage upload
- QA review workflow with repair routing
- provider usage tracking, budget checks, and audit logging
- MCP resources and prompts for reusable VOS knowledge artifacts

Architecture overview and diagrams are documented in [`docs/architecture/project-architecture.md`](docs/architecture/project-architecture.md).

---

## Operating modes

VOS Studio MCP separates generation workflows into two explicit modes.

### `dashboard_manual`

Used when a human operator will execute the generation manually inside a provider dashboard.

The MCP prepares:

- final prompt
- negative prompt, when applicable
- visual direction
- aspect ratio
- provider/model recommendation
- generation settings
- checklist for the operator
- expected output format
- asset naming convention
- QA criteria

The human operator then performs the generation inside the provider UI and registers the resulting asset back into the system.

This mode is useful for exploratory creative work and for workflows where dashboard access is the intended execution path.

### `api_credits`

Used when the MCP executes through an official API, MCP server, CLI, or SDK.

This mode includes:

- provider
- model/tool
- estimated cost
- budget check
- explicit approval
- job ID
- status tracking
- output references
- audit log

This mode is useful for controlled automation, repeatable jobs, and production workflows where cost and permissions are clear.

---

## Core domain model

The core domain entity is the **Creative Sprint**.

A creative sprint represents one structured production cycle for a client, offer, product, or campaign.

A sprint can include:

- client
- brand kit
- product or offer
- campaign objective
- target audience
- campaign angles
- creative brief
- blueprint
- stage-aware assets
- provider jobs
- QA results
- cost estimates
- approvals
- delivery pack

Most MCP tools either create, read, update, or act on a `sprint_id`.

The current domain also treats **assets as stage-aware creative artifacts**, not only storage references. Assets can carry stage, kind, lineage, reference approval, and final-delivery semantics.

---

## Current MCP capabilities

The server now exposes a broader workflow surface than the original bootstrap plan.

Representative tools include:

```text
create_client
save_brand_kit
create_creative_sprint
get_sprint_status
prepare_creative_brief
generate_campaign_angles
prepare_video_blueprint
prepare_execution_pack
register_manual_asset
review_asset_quality
request_api_video
get_video_job_status
list_video_jobs
record_asset_performance
record_performance_metrics
promote_to_library
search_library
list_provider_capabilities
get_provider_usage_summary
set_client_webhook
close_sprint
conclude_variant_test
reset_circuit_breaker
```

The MCP server also exposes reusable **resources and prompts**, such as:

- `vos://playbook`
- `vos://stage-templates/{stage}`
- `vos://providers`
- `vos_creative_brief(...)`
- `vos_shot_direction(...)`

Tool design still optimizes for compact, predictable responses rather than large raw payloads.

A good tool response should remain compact:

```json
{
  "status": "created",
  "sprint_id": "spr_123",
  "summary": "Sprint created and ready for blueprint/execution pack generation.",
  "next_action": "prepare_video_blueprint"
}
```

---

## Provider strategy

Provider integrations are implemented through adapters.

Current provider categories:

- `manual_dashboard`
- `higgsfield`
- `freepik`
- `magnific`
- future official APIs/MCPs/CLIs

Tools should not call provider APIs directly from business logic. They should call internal provider services or adapters.

This keeps the system easier to maintain when providers change pricing, authentication, capabilities, or response formats.

---

## Storage strategy

Large files should not be stored in the MCP response, the database, or the Git repository.

Assets should be stored in external storage such as:

- Cloudflare R2
- S3-compatible object storage
- Google Drive
- another approved storage provider

The MCP should return references:

```json
{
  "asset_id": "asset_123",
  "storage_url": "...",
  "preview_url": "...",
  "metadata": {
    "provider": "higgsfield",
    "mode": "dashboard_manual",
    "sprint_id": "spr_123"
  }
}
```

---

## Persistence strategy

The system of record is Supabase/Postgres.

Postgres stores structured operational data such as:

- clients
- brand kits
- creative sprints
- prompts and presets
- stage-aware assets
- provider jobs
- approvals
- budgets
- provider usage events
- audit events
- deliveries
- performance records

Local development may use a lightweight setup as long as the production schema remains compatible with Postgres.

---

## Cost and approval model

Any action that can spend credits, create API billing, publish content, send client-facing deliverables, or modify external systems must require explicit human approval.

Paid or external actions should include:

```json
{
  "requires_approval": true,
  "estimated_cost": "...",
  "budget_status": "within_budget",
  "approval_token": "..."
}
```

The system should be especially careful with video generation, retries, upscaling, and batch generation because these can become expensive quickly.

---

## Security principles

This project should be treated as private-first and client-safe by design.

Do not commit:

- API keys
- access tokens
- cookies
- provider credentials
- client secrets
- private client data
- raw client assets
- generated deliverables

Use `.env.example` for documenting required environment variables.

Use environment variables or a deployment platform secret manager for real credentials.

Logs and MCP responses must not expose secrets.

---

## Architecture decisions

All architecture decisions are documented in [`docs/adr/`](docs/adr/README.md).

The ADR set now covers the original foundation decisions plus newer domain-evolution work, including:

- the VOS-native domain evolution roadmap
- asset stage and lineage modeling
- BrandKit Asset Lock / campaign visual system v2
- provider usage and operational hardening
- MCP-native resources/prompts for reusable VOS knowledge

Use the ADR index as the source of truth for the current architecture direction.

---

## Expected runtime shape

The project uses Python with the official MCP SDK (FastMCP) for tool definitions, FastAPI for HTTP middleware, and Pydantic v2 for schema validation. Package management is handled by `uv`.

```text
Request
  → FastAPI middleware (auth, correlation, metrics)
  → FastMCP ASGI app (MCP protocol, tool/resource dispatch)
  → tool handler
  → workflow/application services
  → providers / database / storage / async tasks
```

At a high level, the runtime architecture is:

```text
MCP clients
  → MCP tools/resources/prompts
  → workflow services
  → VOS domain model
  → provider adapters / storage / webhooks
  → Postgres + Redis + object storage
```

For full diagrams, see [`docs/architecture/project-architecture.md`](docs/architecture/project-architecture.md).

---

## Development workflow

Development should happen through small pull requests.

Preferred flow:

```text
create branch
  → implement one focused slice
  → run checks
  → open PR
  → review
  → merge
```

Coding agents should work in constrained branches and avoid large unrelated changes.

---

## Current focus

The project has already moved beyond the initial foundation phase.

The current focus is:

- tightening workflow correctness and state semantics
- continuing to refine stage-aware creative execution
- strengthening budget / storage / job-status correctness
- improving learning loops from QA and performance data
- keeping the architecture explicit through ADRs and documentation

### Near-term focus

- continued workflow correctness refinements
- stronger reporting around provider usage and actual spend semantics
- further UX improvements around aggregated job status and delivery readiness
- gradual expansion of reusable playbook/resources/prompts

### Longer-term expansion

- Meta Marketing API integration for performance data
- Google Ads API integration
- TikTok Business API integration
- automated brand kit enrichment from performance data
- additional approved provider integrations where they fit the operating model

---

## Repository status

This project is in an **active architecture and workflow implementation stage**.

The foundation, core domain model, and major workflow surfaces are already in place. The current work is focused more on refinement, correctness, and operational maturity than on basic bootstrapping.

---

## License

License is not defined yet.