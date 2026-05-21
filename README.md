# VOS Studio MCP

VOS Studio MCP is the operational Model Context Protocol server for **VOS Studio**, a performance creative studio focused on AI-assisted creative production for ads, product launches, and e-commerce campaigns.

This project is designed to become the internal creative operations layer that connects briefs, brand kits, creative strategy, prompt packs, generation providers, asset QA, cost controls, approvals, and delivery workflows.

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
  → dashboard execution pack or API generation job
  → asset registration
  → quality review
  → delivery pack
```

The system should make creative production faster, more consistent, easier to audit, and safer to operate with AI tools.

---

## What this server is responsible for

The MCP server is responsible for orchestrating the creative workflow, not for replacing every creative or production decision.

It should manage:

- clients
- brand kits
- creative briefs
- creative sprints
- hooks and angles
- prompt packs
- provider-specific generation settings
- manual dashboard execution packs
- API/credit-based generation jobs
- asset registration
- asset metadata
- creative QA
- approval checkpoints
- delivery packages
- cost estimation and budget limits
- audit logs

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

This mode must include:

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
- creative angles
- hooks
- scripts
- prompt packs
- generation mode
- provider jobs
- assets
- QA results
- cost estimates
- approvals
- delivery pack

Most MCP tools should either create, read, update, or act on a `sprint_id`.

---

## Initial MCP tools

The first version of the server should focus on a small set of workflow-oriented tools instead of many tiny tools.

Recommended initial tools:

```text
create_client
save_brand_kit
create_creative_sprint
prepare_dashboard_pack
estimate_generation_cost
register_manual_asset
review_asset_quality
create_delivery_pack
```

Later tools may include:

```text
run_approved_generation
check_generation_status
sync_provider_history
create_prompt_pack
create_hook_variations
create_static_ad_concepts
create_video_ad_concepts
```

Tool design should optimize for low token cost and predictable agent behavior.

A good tool response should be compact:

```json
{
  "status": "created",
  "sprint_id": "spr_123",
  "summary": "Sprint created with 5 angles, 10 hooks, and 6 prompt packs.",
  "next_action": "prepare_dashboard_pack"
}
```

A tool should not return large raw logs, full provider payloads, or entire asset collections unless explicitly requested.

---

## Provider strategy

Provider integrations should be implemented through adapters.

Initial provider categories:

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

The system of record is expected to be Supabase/Postgres.

Postgres should store structured operational data such as:

- clients
- brand kits
- creative sprints
- prompts
- presets
- assets
- jobs
- approvals
- budgets
- audit events
- deliveries

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

## Architecture Decision Records

Architectural decisions are documented in [`docs/adr`](docs/adr).

Current ADRs:

- ADR-0001 — Use TypeScript as the primary language
- ADR-0002 — Build a remote HTTP MCP server
- ADR-0003 — Separate dashboard_manual and api_credits modes
- ADR-0004 — Do not automate provider dashboards
- ADR-0005 — Require human approval for paid or external actions
- ADR-0006 — Use workflow-oriented tools to reduce token cost
- ADR-0007 — Use Supabase/Postgres as the system of record
- ADR-0008 — Store assets outside the MCP and return references
- ADR-0009 — Use provider adapters for Higgsfield, Freepik, and Magnific
- ADR-0010 — Treat the Creative Sprint as the core domain entity
- ADR-0011 — Keep MCP tool outputs compact and structured
- ADR-0012 — Use explicit cost budgets and generation limits
- ADR-0013 — Keep prompts and presets versioned
- ADR-0014 — Use queues for long-running generation jobs
- ADR-0015 — Implement audit logs for operational traceability
- ADR-0016 — Use environment variables and secret management for credentials
- ADR-0017 — Start private-first and client-safe by design
- ADR-0018 — Use incremental PR-based development with coding agents

Future implementation work should read the ADRs before making architectural changes.

---

## Expected project structure

The initial TypeScript structure should evolve toward:

```text
src/
  server.ts
  tools/
    createClient.ts
    saveBrandKit.ts
    createCreativeSprint.ts
    prepareDashboardPack.ts
    estimateGenerationCost.ts
    registerManualAsset.ts
    reviewAssetQuality.ts
    createDeliveryPack.ts
  schemas/
    client.ts
    brandKit.ts
    sprint.ts
    asset.ts
    job.ts
    approval.ts
  services/
    database.ts
    storage.ts
    auditLog.ts
    costEstimator.ts
    providers/
      manualDashboard.ts
      higgsfield.ts
      freepik.ts
      magnific.ts
  queues/
    generationQueue.ts
  config/
    env.ts
```

This structure may change, but changes should be documented through ADRs when they affect architecture.

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

## Roadmap

### Milestone 0 — Foundation

- ADR foundation
- descriptive README
- TypeScript project setup
- MCP SDK setup
- local development script
- `.env.example`

### Milestone 1 — Minimal MCP server

- remote-capable MCP server
- authentication (OAuth 2.1 + bearer token for dev)
- health/status tool
- basic schema validation
- structured tool output convention

### Milestone 2 — Creative sprint workflow

- client creation
- brand kit creation (full entity per ADR-0024)
- creative sprint creation with budget pre-authorization
- dashboard pack generation
- manual asset registration

### Milestone 3 — Persistence, auditability, and performance learning

- Supabase/Postgres schema with RLS
- audit logs
- asset references
- sprint budget tracking and alerts
- performance records (`record_performance` tool)
- sprint initialization with performance context

### Milestone 4 — Provider adapters

- manual dashboard adapter
- Higgsfield adapter
- Freepik/Magnific adapter planning
- cost estimation interface

### Milestone 5 — Production readiness

- deployment
- rate limits
- secret management
- job queue (Trigger.dev)
- monitoring

### Milestone 6 — Platform integrations (future)

- Meta Marketing API integration for performance data
- Google Ads API integration
- TikTok Business API integration
- automated brand kit enrichment from performance data

---

## Architecture decisions

All architecture decisions are documented as ADRs in [`docs/adr/`](docs/adr/README.md).

The current ADR set covers 25 decisions, including language choice, remote server model, generation modes, security boundaries, persistence, provider adapters, cost controls, sprint budget pre-authorization, audit logging, authentication, schema migrations, job queue technology, adapter interface contract, client data isolation, brand kit entity specification, and the performance feedback loop.

When implementing new features or making structural changes, check the ADR index first. If a decision is not covered by an existing ADR, create one before implementing.

---

## Repository status

This project is in early foundation stage.

At this stage, the most important work is defining the architecture, safety boundaries, and operational model before implementing provider automation.

---

## License

License is not defined yet.
