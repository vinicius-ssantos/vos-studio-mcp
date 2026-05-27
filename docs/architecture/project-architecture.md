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

```mermaid
flowchart TD
    A[MCP Clients<br/>ChatGPT / agents / operators]

    A --> B[MCP Server / Tool Surface<br/>create_creative_sprint<br/>prepare_execution_pack<br/>prepare_video_blueprint<br/>request_api_video<br/>register_manual_asset<br/>review_asset_quality<br/>library / status tools]

    B --> C[Application / Workflow Services<br/>sprint_service<br/>execution_pack_service<br/>blueprint_service<br/>generation_service<br/>asset_service<br/>prompt_library_service<br/>performance_record_service<br/>budget_guard<br/>audit_service]

    B --> R[MCP Resources / Prompts<br/>vos://playbook<br/>vos://stage-templates/{stage}<br/>vos://providers<br/>vos_creative_brief<br/>vos_shot_direction]

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

---

## 2. Core domain model

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

## 3. Creative execution architecture

The VOS workflow is now much closer to the actual production method:
- open sprint,
- prepare blueprint,
- prepare stage-aware execution pack,
- create/register assets by stage,
- run QA,
- repair if needed,
- register final delivery.

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
    D3 --> F[request_api_video or manual provider execution]
    D4 --> G[review_asset_quality]
    D5 --> E

    F --> H[poll_video_job]
    H --> I{provider completed?}

    I -->|no| H
    I -->|yes| J[set generation_status=completed]

    J --> K{media type}
    K -->|video| L[upload_video_to_storage]
    K -->|image| M[upload_image_to_storage]

    L --> N[storage_url + storage_status]
    M --> N

    E --> G
    N --> G

    G --> O{QA outcome}
    O -->|approved| P[approved reference / final delivery]
    O -->|needs_repair| D4
    O -->|rejected| D4
```

---

## 4. API video generation flow

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

## 5. Layered view

The system can also be read as six layers.

```mermaid
flowchart LR
    subgraph L1[Interface Layer]
        A1[MCP Tools]
        A2[MCP Resources / Prompts]
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

## 6. Architectural summary

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

## 7. Relationship to ADRs

This document is descriptive.

The normative architectural direction remains in the ADRs, especially:
- `docs/adr/0031-vos-native-domain-evolution-roadmap.md`
- `docs/adr/0037-*`
- `docs/adr/0038-*`

This file should be updated whenever the runtime architecture or domain model changes in a meaningful way.
