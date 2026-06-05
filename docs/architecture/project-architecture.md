# Project Architecture

This document describes the current architecture of `vos-studio-mcp` after the VOS-native domain evolution work.

It focuses on:
- the main runtime layers,
- the stage-aware VOS domain,
- the generation and execution flows,
- and the relationship between MCP tools, workflows, providers, persistence, and async workers.

---

## 1. Architecture overview

The current architecture is organized as:
- a thin MCP interface layer,
- an application/workflow layer,
- a stronger VOS creative domain,
- provider and storage integration layers,
- asynchronous background workers,
- and Postgres/Redis/object storage as infrastructure.

In addition to tools, the server also exposes MCP-native resources and prompts. These are read-only, stateless knowledge artifacts and should be understood as a knowledge surface, not as part of the transactional workflow path.

```mermaid
flowchart TD
    A[MCP Clients<br/>ChatGPT / agents / operators]

    A --> B[MCP Server / Tool Surface<br/>create_creative_sprint<br/>prepare_execution_pack<br/>prepare_video_blueprint<br/>request_api_video<br/>register_manual_asset<br/>review_asset_quality<br/>library / status tools]

    B --> C[Application / Workflow Services<br/>sprint_service<br/>execution_pack_service<br/>blueprint_service<br/>generation_service<br/>asset_service<br/>prompt_library_service<br/>performance_record_service<br/>budget_guard<br/>audit_service]

    B --> R[MCP Resources / Prompts<br/>read-only, stateless<br/>vos://playbook<br/>vos://stage-templates/{stage}<br/>vos://providers<br/>vos_creative_brief<br/>vos_shot_direction]

    C --> D[VOS Creative Domain<br/>Sprint<br/>BrandKit + Asset Lock<br/>Asset<br/>VariantGroup / Variant<br/>PerformanceRecord<br/>ProviderUsageEvent]

    C --> E[Provider Adapters<br/>Higgsfield<br/>Freepik<br/>Magnific<br/>Manual Dashboard]

    C --> F[Control / Policy Layer<br/>auth guards<br/>tenant context + RLS<br/>rate limiter<br/>budget checks<br/>audit trail]

    C --> G[Async Tasks / Workers<br/>poll_video_job<br/>upload_video_to_storage<br/>upload_image_to_storage<br/>webhook follow-ups]

    D --> H[(Postgres / Supabase)]
    F --> H
    G --> H

    E --> I[External Providers<br/>video generation<br/>image generation<br/>upscaling<br/>manual dashboards]

    G --> J[Object Storage<br/>media URLs / previews]

    I --> G
```

### Scope note

The tool surface shown above is a high-level summary, not a complete tool inventory. The current server also exposes workflow and operations tools such as sprint status, provider usage summary, provider capability listing, client webhook configuration, variant conclusion, circuit breaker reset, creative brief preparation, and campaign angle generation.

---

## 2. Vocabulary conventions

To keep the business language and the implementation language aligned, this document uses the following conventions:

- **Business stage names**: Stage 0, Stage A, Stage B, Stage C, Repair, Final
- **Internal stage identifiers**: `stage_0`, `stage_a`, `stage_b`, `stage_c`, `repair`, `final`
- **Asset Lock**: the campaign visual system / constraint layer used by VOS; the persisted field name is `asset_lock`
- **Operating modes**: the exact internal mode names are `dashboard_manual` and `api_credits`
- **Delivery readiness**: business readiness for a downstream step or final handoff; distinct from provider completion and distinct from storage upload completion

In other words:
- provider completion does not always mean storage completion
- storage completion does not always mean delivery readiness
- the Final stage is a business-stage concept, not just a storage state

---

## 3. Core domain model

The most important architectural change is that the domain is now more explicitly VOS-native.

The system no longer treats assets as only generic outputs. Instead, assets can now carry stage, kind, lineage, reference approval, and final-delivery semantics.

Main domain concepts:
- `Sprint`
- `BrandKit`
- `Asset Lock`
- `Asset` with stage-aware metadata
- `VariantGroup` / `Variant`
- `PerformanceRecord`
- `ProviderUsageEvent`

```mermaid
flowchart LR
    A[Sprint] --> B[BrandKit]
    B --> C[Asset Lock]

    A --> D[Assets]

    subgraph D[Assets by stage]
        D1[stage_0<br/>anchor]
        D2[stage_a<br/>character sheet]
        D3[stage_b<br/>storyboard]
        D4[stage_c<br/>video]
        D5[repair]
        D6[final]
    end

    D1 --> D2
    D1 --> D3
    D2 --> D3
    D3 --> D4
    D4 --> D5
    D4 --> D6
    D5 --> D6

    A --> E[VariantGroup / Variant]
    A --> F[ProviderUsageEvent]
    A --> G[PerformanceRecord]

    D --> G
```

### Domain notes

- `BrandKit` remains the main campaign identity record.
- `asset_lock` adds more explicit campaign visual constraints.
- `Asset` is now the central creative artifact record, not just a storage reference.
- The sprint remains the operational container for the campaign workflow.

---

## 4. Creative execution architecture

The VOS workflow is now much closer to the actual production method:
- open sprint,
- prepare blueprint,
- prepare stage-aware execution pack,
- create/register assets by stage,
- run QA,
- repair if needed,
- register final delivery.

The most important nuance is that Stage C can now follow two distinct execution paths:
- an API path, which creates a provider job and then relies on polling/upload,
- or a manual provider path, where a human operator creates the asset and registers it directly.

```mermaid
flowchart TD
    A[create_creative_sprint] --> B[Sprint + BrandKit context]
    B --> C[prepare_video_blueprint]
    B --> D[prepare_execution_pack]

    D --> D0[stage_0 pack<br/>anchor image]
    D --> D1[stage_a pack<br/>character sheet]
    D --> D2[stage_b pack<br/>storyboard]
    D --> D3[stage_c pack<br/>video]
    D --> D4[repair pack]
    D --> D5[final pack]

    D0 --> E[register_manual_asset]
    D1 --> E
    D2 --> E

    D3 --> F1[API path<br/>request_api_video]
    D3 --> F2[Manual path<br/>provider dashboard / editor]
    F2 --> E

    F1 --> H[poll_video_job]
    H --> I{provider completed?}

    I -->|no| H
    I -->|yes| J[set generation_status=completed]
    J --> K[set storage_status=pending]
    K --> L[upload_video_to_storage]
    L --> N[storage_url + storage_status]

    D4 --> G[review_asset_quality]
    D5 --> E

    E --> G
    N --> G

    G --> O{QA outcome}
    O -->|approved| P[approved reference / final delivery]
    O -->|needs_repair| D4
    O -->|rejected| D4
```

### Important note

`upload_image_to_storage` exists in the system, but it belongs to image-provider completion paths and webhook/media-routing flows. It is not part of the `request_api_video()` path, which is currently video-only and bound to Higgsfield.

---

## 5. API video generation flow

The API-driven generation path is the most operationally sensitive workflow in the system because it combines:
- authentication,
- rate limiting,
- provider budget checks,
- sprint budget enforcement,
- provider submission,
- asset creation,
- async polling,
- storage upload,
- and eventual reconciliation.

```mermaid
flowchart TD
    A[request_api_video] --> B[auth + rate limit]
    B --> C[get higgsfield adapter]
    C --> D[estimate_cost]
    D --> E[validate sprint]
    E --> F[check sprint budget]
    F --> G[check sprint max_videos]
    G --> H[check provider budget<br/>create usage event]
    H --> I[open new session]
    I --> J[SELECT Sprint FOR UPDATE]
    J --> K[re-check sprint budget under lock]
    K --> L[submit provider job]
    L --> M[create Asset<br/>provider_job_id<br/>provider_usage_event_id]
    M --> N[increment Sprint.spent_usd]
    N --> O[commit]
    O --> P[enqueue poll_video_job]

    P --> Q[poll provider status]
    Q --> R{status}

    R -->|queued/running| Q
    R -->|failed| S[mark failed + audit + notify]
    R -->|completed| T[mark generation completed]
    T --> U[set storage_status=pending]
    U --> V[enqueue upload_video_to_storage]
    V --> W[store media]
    W --> X[storage_status=stored]
    T --> Y[record_actual_cost best-effort]
```

### Important note

The current architecture distinguishes between:
- provider job completion,
- storage upload progression,
- and final asset availability.

This is important because an asset can be generation-complete while still not fully available in final storage.

---

## 6. Layered view

The system can also be read as six layers.

```mermaid
flowchart LR
    subgraph L1[Interface Layer]
        A1[MCP Tools]
        A2[MCP Resources / Prompts<br/>read-only / stateless]
    end

    subgraph L2[Workflow Layer]
        B1[Sprint workflows]
        B2[Execution pack workflows]
        B3[Blueprint workflows]
        B4[Generation workflows]
        B5[QA workflows]
        B6[Library / performance workflows]
    end

    subgraph L3[Domain Layer]
        C1[Sprint]
        C2[BrandKit]
        C3[Asset Lock]
        C4[Asset stage-aware]
        C5[Lineage / references]
        C6[Performance memory]
        C7[Provider usage ledger]
    end

    subgraph L4[Integration Layer]
        D1[Provider adapters]
        D2[Storage service]
        D3[Webhook routes]
    end

    subgraph L5[Async Layer]
        E1[Polling]
        E2[Upload]
        E3[Notifications]
        E4[Cost reconciliation]
    end

    subgraph L6[Infrastructure Layer]
        F1[(Postgres / Supabase)]
        F2[(Redis)]
        F3[(Object Storage)]
    end

    A1 --> B1
    A1 --> B2
    A1 --> B3
    A1 --> B4
    A1 --> B5
    A1 --> B6
    A2 --> B2
    A2 --> B3

    B1 --> C1
    B2 --> C2
    B2 --> C3
    B3 --> C4
    B4 --> C4
    B5 --> C5
    B6 --> C6
    B4 --> C7

    B4 --> D1
    B4 --> D2
    D3 --> E2

    B1 --> F1
    B2 --> F1
    B3 --> F1
    B4 --> F1
    B5 --> F1
    B6 --> F1

    B4 --> F2
    E1 --> F1
    E2 --> F1
    E2 --> F3
```

---

## 7. Architectural summary

### What is strong now

- Thin MCP tool layer
- Real provider adapter abstraction
- Stronger stage-aware domain model
- Asset Lock support in BrandKit
- Async job polling and storage upload separation
- Budget and audit controls integrated into the workflow layer
- MCP resources/prompts for reusable knowledge artifacts

### What this architecture optimizes for

- operational control,
- repeatable creative execution,
- auditability,
- provider isolation,
- and alignment with the VOS production method.

### What still deserves ongoing review

- status aggregation semantics for batch job views,
- sprint budget truth vs actual billed cost semantics,
- and continued tightening of the generation workflow state machine as the system evolves.

---

## 8. Known nuances in the current `main`

This document is intended to describe the current runtime architecture accurately, but a few nuances are worth calling out explicitly:

- The individual job status path is storage-aware, but aggregated job views still deserve review so they do not sound more final than the underlying storage state.
- The API video path clearly re-checks sprint budget under row lock. Limit semantics around `max_videos` should continue to be reviewed alongside the request-time concurrency model.
- The current cost reconciliation path is operationally useful, but the semantics of “actual billed cost” vs “estimate confirmed” should continue to be made clearer over time.

These are not architecture-breakers, but they are the kinds of details that affect how precisely the workflow layer communicates system state.

---

## 9. Relationship to ADRs

This document is descriptive.

The normative architectural direction remains in the ADRs, especially:
- `docs/adr/0039-vos-native-domain-evolution-roadmap.md`
- `docs/adr/0037-*`
- `docs/adr/0038-*`

This file should be updated whenever the runtime architecture or domain model changes in a meaningful way.
