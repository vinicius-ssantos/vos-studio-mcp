# ADR-0025 — Performance feedback loop and creative learning

Status: Accepted  
Date: 2026-05-21

## Context

VOS Studio MCP currently ends its workflow at delivery: brief → sprint → generation → QA → delivery pack. For a performance creative agency, this is incomplete. The value of creative production is measured by what happens after delivery — which assets ran, which converted, which angles resonated with the target audience.

Without a feedback loop, every sprint starts from zero. The system cannot distinguish a hook that consistently drives CTR from one that has been tried and failed. Proven angles are lost in spreadsheets or in the memory of individual team members. The brand kit's `performance` block (ADR-0024) has nowhere to pull data from.

The missing loop is: **deliver → measure → record → inform next sprint**.

This feedback loop is what transforms the MCP from a production system into an institutional creative intelligence system — one that gets better over time and creates a compounding advantage for the agency.

## Decision

Introduce a `PerformanceRecord` entity that links creative assets to their measured results on distribution platforms.

```python
from typing import Literal
from pydantic import BaseModel, Field


class DistributionContext(BaseModel):
    platform: str
    ad_account_id: str | None = None
    campaign_id: str | None = None
    ad_set_id: str | None = None
    ad_id: str | None = None
    start_date: str
    end_date: str | None = None


class PerformanceMetrics(BaseModel):
    impressions: int | None = None
    clicks: int | None = None
    ctr: float | None = None
    spend_usd: float | None = None
    conversions: int | None = None
    cpa_usd: float | None = None
    roas: float | None = None
    thumb_stop_rate: float | None = None
    hook_retention_rate: float | None = None
    quality_score: str | None = None


class PerformanceClassification(BaseModel):
    performance_tier: Literal["top", "average", "underperformer", "untested"]
    winning_elements: list[str] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)
    notes: str | None = None


class PerformanceRecord(BaseModel):
    id: str
    asset_id: str
    sprint_id: str
    client_id: str
    brand_kit_id: str
    distribution: DistributionContext
    metrics: PerformanceMetrics
    classification: PerformanceClassification
    recorded_at: str
    recorded_by: str
```


Performance records are created via a dedicated tool `record_performance` and are **never** auto-generated from platform APIs in the initial implementation. The operator registers results manually or via a future integration tool. This keeps the system useful before platform API integrations exist.

The feedback loop closes through two mechanisms:

**1. Brand kit enrichment (automatic):** When a `PerformanceRecord` is classified as `top`, the system automatically proposes additions to the brand kit's `performance.provenAngles`, `performance.provenHooks`, and `performance.topAssetRefs`. The operator approves before the brand kit is updated (ADR-0005 approval model applies).

**2. Sprint initialization (query-based):** When `create_creative_sprint` is called, the tool queries `PerformanceRecord` for the same client and returns a `performance_context` block in the response:

```json
{
  "sprint_id": "spr_789",
  "performance_context": {
    "top_angles": ["urgency + scarcity", "social proof + transformation"],
    "proven_hooks": ["Você ainda está perdendo dinheiro com..."],
    "avoid": ["lifestyle without product", "soft CTAs"],
    "top_asset_refs": ["asset_111", "asset_222"]
  },
  "next_action": "prepare_dashboard_pack"
}
```

This gives the agent (and human operator) immediate creative direction grounded in what actually worked for this client.

## Alternatives considered

- **Auto-pull from platform APIs (Meta, Google, TikTok)**: the correct long-term approach, but requires OAuth integrations with each ad platform. Too much complexity for the current stage. Deferred to a future milestone.
- **No performance feedback**: rejected. This is the most important strategic differentiator of the system. Without it, the MCP is a production tool, not a learning system.
- **Free-text notes on assets**: simple but unqueryable. Cannot inform sprint creation programmatically. Rejected.
- **Manual records with structured schema and query-driven feedback**: selected. Usable immediately, queryable, extensible to API integration later.

## Consequences

The `PerformanceRecord` entity creates a new data category that must be protected under the same RLS rules as client sprints and assets (ADR-0023). Performance data is commercially sensitive — a client's CTR and ROAS data must not be visible to other clients.

The quality of the learning loop depends entirely on the consistency of record input. If operators do not record performance data, the brand kit's `performance` block stays empty and sprint initialization returns no context. Adoption of `record_performance` must be part of the agency's delivery workflow, not optional.

Platform API integrations (Meta Marketing API, Google Ads API, TikTok Business API) are the natural next step and should be planned as a Milestone 6 scope.

## Impact on VOS Studio MCP

- Create `src/vos_studio_mcp/schemas/performance.py` with the full Pydantic schema.
- Create `src/vos_studio_mcp/tools/record_performance.py` as a new tool in Milestone 3.
- Update `src/vos_studio_mcp/tools/create_creative_sprint.py` to query performance records and return `performance_context` in the response.
- Update `src/vos_studio_mcp/services/database.py` to include a `get_top_performers(client_id, brand_kit_id)` query helper.
- Add `performance` to `src/vos_studio_mcp/schemas/brand_kit.py` as a derived read-only block populated from `PerformanceRecord`.
- Add `performanceRecord` RLS policy to Milestone 3 schema migrations.
- The brand kit update from a `top` performance record must go through the existing approval model (ADR-0005) before being committed.
