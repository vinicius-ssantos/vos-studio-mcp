# ADR-0039 — Evolve the architecture toward a VOS-native creative domain

Status: Proposed  
Date: 2026-05-26

## Context

The current `vos-studio-mcp` architecture is already strong as a creative operations system.

The project has:
- thin MCP tools delegating to service-layer logic,
- provider adapters for Higgsfield, Freepik, Magnific, and manual dashboard execution,
- asynchronous workers for long-running generation and storage tasks,
- Postgres + RLS as the system of record,
- audit logging,
- provider usage ledger,
- rate limiting,
- and an ADR-driven architecture practice.

This architecture is already appropriate for a performance creative agency workflow.

However, the current domain is still more strongly modeled as a **creative ops system** than as a **VOS-native creative production system**.

Today, the main domain entities are centered around:
- `Sprint`,
- `Asset`,
- `ProviderUsageEvent`,
- `PerformanceRecord`,
- `BrandKit` as flexible JSON-backed identity/visual/restrictions/performance memory.

That is operationally useful, but it under-models the actual VOS production method, which is stage-based and artifact-driven.

The VOS method depends on intermediate creative artifacts such as:
- anchor image,
- character sheet,
- storyboard,
- video blueprint,
- repair variants,
- approved references.

The current architecture does not yet represent those artifacts explicitly enough in the domain. As a result:
- the system is better at registering and orchestrating outputs than at expressing the internal creative method,
- parts of the creative lifecycle are implicit rather than modeled,
- and some state, cost, and business-rule transitions are spread across services and tasks instead of being explicit in the domain.

## Problem statement

The project does **not** need a full rewrite.

The problem is not that the architecture is wrong. The problem is that the current architecture is **not yet specific enough to the VOS production method**.

The main architectural gaps are:

### 1. The creative domain is under-modeled

`Asset` behaves mostly as a generic generated/manual output registry. It does not yet encode:
- stage,
- artifact role,
- lineage,
- approved reference status,
- repair relationship,
- delivery readiness.

### 2. State machines are implicit

The lifecycle of a generated video is currently spread across:
- provider completion,
- `generation_status`,
- `storage_status`,
- upload worker behavior,
- and API/tool responses for job status.

This makes it possible for "provider completed" to be interpreted too close to "asset ready".

### 3. Generation orchestration is becoming too concentrated

`request_api_video()` currently handles:
- auth,
- rate limiting,
- cost estimate,
- sprint validation,
- sprint budget validation,
- video-count validation,
- provider quota validation,
- provider submission,
- asset creation,
- sprint spend update,
- polling enqueue,
- audit logging.

This is still manageable, but it is already the clearest sign that the workflow layer needs more explicit structure.

### 4. `BrandKit` is strategically important but structurally too loose

ADR-0024 describes BrandKit as one of the richest and most important inputs in the system, especially for consistency and anti-drift.

But the current model stores it primarily as JSONB blocks (`identity`, `visual`, `restrictions`, `performance_memory`), which is flexible but weak as a contract for downstream creative services.

### 5. Financial correctness is split across layers

The current system tracks:
- sprint spend (`Sprint.spent_usd`),
- provider estimated usage,
- and potentially actual provider cost via the provider usage ledger.

But the request path increments sprint spend using estimated cost, and the completion path does not yet clearly reconcile actual billed cost back into the ledger or sprint-level accounting.

### 6. Business-rule enforcement is vulnerable to concurrency gaps

`request_api_video()` validates sprint budget and limits in one session, performs provider quota checks, then re-enters another session to commit asset creation and increment spend. That leaves a concurrency window in which simultaneous requests may both pass validation and commit.

## Decision

The architecture will evolve **incrementally** toward a more explicit **VOS-native creative domain**, while preserving the current macro-architecture:

- MCP tools remain thin,
- service layer remains the main application boundary,
- provider adapters remain the integration boundary,
- workers remain responsible for long-running async work,
- Postgres + RLS remains the system of record,
- Redis remains the rate-limit and queue support layer,
- storage remains external.

The change is **not** a rewrite of architecture style. It is a **domain refinement and workflow clarification initiative**.

## Architectural direction

### We will keep

#### 1. Thin MCP tools

Tools should continue to be a transport and interface layer only. They should validate inputs, invoke the appropriate application service, and return compact structured outputs.

#### 2. Service-layer orchestration

Application services remain the main place for workflow coordination, access control, validation, and transactional behavior.

#### 3. Provider adapters

The adapter pattern is correct and should remain the integration seam for provider APIs and manual execution paths.

#### 4. Async workers

Polling, upload, durable notifications, and other long-running tasks should remain outside the request-response path.

#### 5. Postgres + RLS as the system of record

This remains the correct persistence backbone for multitenant agency operations.

### We will change

#### 1. The domain model will become stage-aware

The central change is that the domain must stop treating all assets as equivalent outputs.

The system will explicitly model creative artifacts by stage and role.

##### New core concepts to introduce

At minimum, the domain should support:

- `asset_stage`
  - `stage0_anchor`
  - `stageA_character_sheet`
  - `stageB_storyboard`
  - `stageC_video`
  - `repair`
  - `final_delivery`

- `asset_kind`
  - `image`
  - `video`
  - `document`
  - `blueprint`
  - `prompt_pack`

- lineage and reference metadata
  - `source_asset_id`
  - `reference_asset_ids`
  - `approved_as_reference`
  - `delivery_ready`

This change keeps `Asset` as the central artifact record, but upgrades it from a generic registry to a stage-aware creative object.

#### 2. The workflow layer will become more explicit

High-value workflows will be decomposed into clearer application steps rather than growing inside a single large orchestration method.

For example, `request_api_video()` should conceptually evolve into smaller responsibilities such as:
- validate generation request,
- reserve or request budget,
- submit provider job,
- register asset and job linkage,
- enqueue follow-up workflow,
- emit audit trail.

This may still be implemented within one service module, but the architecture should treat these as explicit workflow steps rather than one large unit of orchestration.

#### 3. Asset lifecycle state will become explicit

The system should separate:
- provider generation lifecycle,
- storage lifecycle,
- delivery readiness lifecycle.

At minimum, the architecture should distinguish:
- `requested`,
- `provider_pending`,
- `provider_running`,
- `provider_completed`,
- `upload_pending`,
- `stored`,
- `failed`.

This does **not** necessarily require a single new enum immediately, but the architecture should move away from implying that `generation_status=completed` means the asset is ready for downstream use.

#### 4. BrandKit will evolve into BrandKit + Asset Lock semantics

The current BrandKit concept is correct, but too weakly enforced.

Architecturally, BrandKit should converge toward a richer campaign visual system and asset lock object that can reliably constrain downstream blueprint, execution, QA, and repair flows.

This includes explicit support for concepts such as:
- dominant register,
- secondary register,
- forbidden register,
- allowed materials,
- forbidden materials,
- allowed environments,
- forbidden environments,
- text policy,
- endcard policy,
- approved visual references.

This evolution must stay consistent with the intent of ADR-0024 rather than creating a second disconnected concept for creative constraints.

#### 5. Financial flow will be modeled as an end-to-end lifecycle

The architecture should explicitly connect:
- budget validation,
- estimated cost reservation,
- request-time spend accounting,
- actual provider cost reconciliation,
- sprint-level budget truth.

This means the system should be able to answer, consistently:
- what was estimated,
- what was actually billed,
- what was reserved at request time,
- what the sprint has truly consumed.

#### 6. Sprint-level budget enforcement must become concurrency-safe

The architecture must treat sprint budget and generation limits as business invariants, not best-effort checks.

Rate limiting is helpful, but it is not sufficient. Sprint-level enforcement must be transaction-safe under concurrent requests.

## Target architecture

The target architecture is still layered, but with a stronger domain core.

### 1. Interface layer

Responsibilities:
- MCP transport,
- schema validation,
- call into application workflows,
- return compact structured outputs.

Examples:
- `create_creative_sprint`
- `request_api_video`
- `prepare_dashboard_pack`
- future stage-aware execution tools.

### 2. Workflow and application layer

Responsibilities:
- orchestrate domain steps,
- validate permissions,
- enforce business rules,
- coordinate provider, storage, and task side effects,
- manage transactions.

Examples:
- sprint creation workflow,
- execution pack preparation,
- generation submission workflow,
- quality review workflow,
- promotion to library workflow.

### 3. Domain layer

Responsibilities:
- represent the actual VOS method and business entities.

Core domain concepts:
- `Sprint`
- `BrandKit` / `AssetLock`
- `Asset` (stage-aware, lineage-aware)
- `VariantGroup`
- `PerformanceRecord`
- `ProviderUsageEvent`

This is the layer that needs the biggest refinement.

### 4. Integration layer

Responsibilities:
- talk to providers,
- talk to storage,
- ingest webhooks,
- hide third-party protocol specifics.

Examples:
- Higgsfield adapter,
- Freepik adapter,
- Magnific adapter,
- manual dashboard adapter,
- storage service.

### 5. Async processing layer

Responsibilities:
- poll long-running jobs,
- upload assets to storage,
- send outbound notifications,
- perform follow-up reconciliation.

Examples:
- `poll_video_job`
- `upload_video_to_storage`
- webhook notification tasks.

### 6. Infrastructure layer

Responsibilities:
- persistence,
- multitenancy,
- queues,
- rate limiting,
- logging and observability.

Examples:
- database service and tenant context,
- Redis rate limiter,
- audit log persistence,
- provider usage ledger.

## Migration strategy

The migration strategy is incremental and issue-driven.

### Phase 1 — Domain correction

Goals:
- align BrandKit contract with real consumers,
- add stage, kind, and lineage to assets,
- make media handling type-aware,
- make status flows aware of storage readiness.

This phase makes the domain more truthful without changing the macro-architecture.

### Phase 2 — Workflow correction

Goals:
- make manual execution packs stage-aware,
- make blueprint generation reflect the actual VOS playbook,
- formalize QA,
- reconcile actual cost and sprint-level budget truth,
- make request-time budget and limit enforcement transaction-safe.

This phase improves correctness and operational predictability.

### Phase 3 — Protocol-native refinement

Goals:
- expose reusable artifacts as MCP resources and prompts,
- evaluate provider-native MCP integration paths,
- improve ranking and learning loops,
- harden production auth behavior.

This phase improves ergonomics and product maturity rather than core correctness.

## Consequences

### Positive consequences

#### 1. The system becomes more faithful to the VOS method

The architecture will not just orchestrate generation jobs; it will represent the actual stages and artifacts of the production method.

#### 2. Downstream services become more reliable

Blueprint generation, QA, repair, library promotion, and delivery flows become easier to reason about when artifact roles are explicit.

#### 3. State and readiness become less ambiguous

Separating provider completion from storage completion reduces false assumptions in status reporting and next-action guidance.

#### 4. Budget behavior becomes more trustworthy

Explicit cost reconciliation and concurrency-safe enforcement strengthen the operational backbone of paid generation workflows.

#### 5. Architectural complexity remains controlled

Because this is an incremental evolution, the project retains its current strengths:
- thin interface layer,
- adapters,
- async workers,
- RLS-backed persistence,
- operational observability.

### Negative consequences and costs

#### 1. The domain model becomes richer and therefore heavier

Adding stage-aware artifacts and stronger BrandKit semantics increases schema complexity, migration cost, and test surface.

#### 2. Some existing service code will need refactoring

Especially `generation_service` and parts of status and storage flow.

#### 3. More explicit state modeling may introduce temporary transition complexity

As the system migrates from implicit lifecycle handling to explicit lifecycle semantics, there may be a period where both models coexist.

## Alternatives considered

### 1. Rewrite the system around full DDD aggregates and commands

Rejected. Too much structural disruption for too little immediate operational gain.

### 2. Keep the architecture exactly as-is and only patch bugs

Rejected. The system would remain operationally useful, but it would continue under-modeling the actual creative method, making future expansion noisier and less coherent.

### 3. Split creative domain into a completely separate subsystem from ops

Rejected for now. The current project benefits from keeping creative artifacts, budget, provider usage, QA, and performance linked inside one operational backbone.

### 4. Continue expanding provider integrations before refining the domain

Rejected as current priority. The most urgent gaps are in domain truthfulness, state correctness, budget correctness, and stage-awareness, not in adding more provider surfaces.

## Out of scope

This ADR does **not** mandate:
- a full rewrite,
- a switch away from FastAPI or FastMCP,
- a move away from SQLAlchemy or Postgres,
- a replacement of Redis or Celery,
- immediate adoption of provider-native MCP backends,
- a new standalone asset microservice.

## Impact on repository structure

This ADR implies gradual changes in:
- `db/models.py`
- `schemas/brand_kit.py`
- `services/generation_service.py`
- `services/blueprint_service.py`
- `services/asset_service.py`
- `services/providers/*`
- task modules for polling and upload
- tool handlers for execution, status, and QA
- tests across services, tasks, integration, and provider-contract layers.

## Implementation notes

This ADR should be realized through the current issue backlog rather than a single large PR.

The most important implementation themes are:
- stage-aware assets,
- BrandKit and Asset Lock convergence,
- blueprint and playbook alignment,
- manual execution packs by stage,
- media-type-aware completion and storage,
- QA formalization,
- cost reconciliation,
- transaction-safe enforcement of sprint-level budget rules.

## Final statement

The architecture is already strong enough for creative operations.

The next step is not to replace it. The next step is to make it **truer to the VOS creative method**.

In practical terms:
- keep the macro-architecture,
- refine the domain,
- clarify workflows,
- make states explicit,
- make budget logic correct,
- and let the system evolve from a good creative ops server into a truly VOS-native production system.
