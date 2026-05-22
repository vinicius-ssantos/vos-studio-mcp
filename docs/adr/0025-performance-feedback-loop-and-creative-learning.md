# ADR-0025 — Performance feedback loop and creative learning

Status: Amended  
Date: 2026-05-21  
Amended: 2026-05-22

## Context

VOS Studio MCP currently ends its workflow at delivery: brief → sprint → generation → QA → delivery pack. For a performance creative agency, this is incomplete. The value of creative production is measured by what happens after delivery — which assets ran, which converted, which angles resonated with the target audience.

Without a feedback loop, every sprint starts from zero. The system cannot distinguish a hook that consistently drives CTR from one that has been tried and failed. Proven angles are lost in spreadsheets or in the memory of individual team members. The brand kit's `performance_memory` block (ADR-0024) has nowhere to pull data from.

The missing loop is: **deliver → measure → record → inform next sprint**.

## Decision

**Phase 1 (implemented — Milestone 4):** Introduce lightweight performance recording directly on the `Asset` entity. The operator records results via the `record_asset_performance` tool after a campaign runs:

```python
class PerformanceInput(BaseModel):
    asset_id: str
    sprint_id: str
    client_id: str
    brand_kit_id: str
    performance_score: int           # 1–10
    performance_label: Literal["top_performer", "average", "underperformer"]
    notes: str | None = None
    angle_label: str | None = None   # appended to brand kit proven_angles if top_performer
    hook_label: str | None = None    # appended to brand kit proven_hooks if top_performer
    description: str | None = None   # appended to brand kit failed_approaches if underperformer
```

Performance data is stored as columns on the `assets` table (`performance_score`, `performance_label`, `performance_notes`) — no separate `PerformanceRecord` table in Phase 1.

The feedback loop closes through brand kit enrichment: when `performance_label` is `top_performer`, the service appends `angle_label` to `brand_kit.performance_memory["proven_angles"]` and `hook_label` to `brand_kit.performance_memory["proven_hooks"]`. When `performance_label` is `underperformer`, `description` is appended to `brand_kit.performance_memory["failed_approaches"]`. These mutations happen in the same transaction with no separate approval step — the operator's explicit call to `record_asset_performance` is the approval act.

**Phase 2 (deferred):** A full `PerformanceRecord` entity with structured distribution context (`platform`, `ad_account_id`, `campaign_id`, `start_date`) and quantitative metrics (`impressions`, `clicks`, `ctr`, `spend_usd`, `conversions`, `roas`, `thumb_stop_rate`) will be introduced when platform API integrations are available (Meta Marketing API, Google Ads API, TikTok Business API). This will enable the `create_creative_sprint` tool to return a `performance_context` block with `top_angles`, `proven_hooks`, and `avoid` lists derived from historical records — giving the agent immediate creative direction grounded in what actually worked for this client.

Phase 2 schema (deferred):

```python
class DistributionContext(BaseModel):
    platform: str
    ad_account_id: str | None = None
    campaign_id: str | None = None
    ad_set_id: str | None = None
    start_date: str
    end_date: str | None = None

class PerformanceMetrics(BaseModel):
    impressions: int | None = None
    clicks: int | None = None
    ctr: float | None = None
    spend_usd: float | None = None
    conversions: int | None = None
    roas: float | None = None
    thumb_stop_rate: float | None = None
    hook_retention_rate: float | None = None

class PerformanceRecord(BaseModel):
    id: str
    asset_id: str
    sprint_id: str
    client_id: str
    brand_kit_id: str
    distribution: DistributionContext
    metrics: PerformanceMetrics
    performance_label: Literal["top_performer", "average", "underperformer"]
    notes: str | None = None
    recorded_at: str
```

## Alternatives considered

- **Auto-pull from platform APIs (Meta, Google, TikTok)**: the correct long-term approach, but requires OAuth integrations with each ad platform. Deferred to Phase 2.
- **No performance feedback**: rejected. This is the most important strategic differentiator of the system. Without it, the MCP is a production tool, not a learning system.
- **Free-text notes on assets**: simple but unqueryable. Cannot inform sprint creation programmatically. Rejected as the only mechanism.
- **Separate `PerformanceRecord` table from day one**: rejected for Phase 1 — adds schema complexity before the query patterns that justify it (platform metrics, distribution context) are implemented. Columns on `assets` are sufficient for the initial feedback loop.
- **Approval gate before brand kit enrichment**: considered, per ADR-0005. Rejected for Phase 1 — the operator's explicit invocation of `record_asset_performance` is itself the approval act. A separate approval step adds friction without security benefit for internal-operator actions.

## Consequences

The quality of the learning loop depends entirely on the consistency of record input. If operators do not call `record_asset_performance` after campaigns run, the brand kit's `performance_memory` stays empty. Adoption of this tool must be embedded in the agency's delivery workflow.

Phase 2 `PerformanceRecord` records must be protected under the same RLS rules as sprints and assets (ADR-0023) — performance data (CTR, ROAS, spend) is commercially sensitive.

## Implementation

- `src/vos_studio_mcp/schemas/performance.py` — `PerformanceInput` / `PerformanceResponse`
- `src/vos_studio_mcp/services/performance_service.py` — `record_asset_performance()` service
- `src/vos_studio_mcp/tools/record_asset_performance.py` — MCP tool
- `db/migrations/versions/0002_add_performance_fields.py` — adds `performance_score`, `performance_label`, `performance_notes` to `assets` and `performance_memory` JSONB to `brand_kits`

## Impact on VOS Studio MCP

- Phase 2: create a `performance_records` table with RLS, add `get_top_performers(client_id, brand_kit_id)` query helper, update `create_creative_sprint` to return a `performance_context` block.
- Phase 2: add platform API integrations (Meta Marketing API, Google Ads API, TikTok Business API) to populate `PerformanceRecord` automatically.
