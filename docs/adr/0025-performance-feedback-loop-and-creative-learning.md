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

```typescript
interface PerformanceRecord {
  id: string;
  assetId: string;
  sprintId: string;
  clientId: string;
  brandKitId: string;

  distribution: {
    platform: 'meta' | 'google' | 'tiktok' | 'youtube' | 'linkedin' | string;
    adAccountId?: string;
    campaignId?: string;
    adSetId?: string;
    adId?: string;
    startDate: string;
    endDate?: string;
  };

  metrics: {
    impressions?: number;
    clicks?: number;
    ctr?: number;            // click-through rate as decimal
    spend_usd?: number;
    conversions?: number;
    cpa_usd?: number;        // cost per acquisition
    roas?: number;           // return on ad spend
    thumbStopRate?: number;  // for video: % who stopped scrolling
    hookRetentionRate?: number; // for video: % who watched past 3s
    qualityScore?: string;   // platform-assigned quality signal
  };

  classification: {
    performanceTier: 'top' | 'average' | 'underperformer' | 'untested';
    winningElements: string[];   // e.g. ["urgency hook", "dark background", "close-up product"]
    failureReasons?: string[];   // e.g. ["weak CTA", "audience mismatch"]
    notes?: string;
  };

  recordedAt: string;
  recordedBy: string;         // agent or human operator ID
}
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

- Create `src/schemas/performance.ts` with the full Zod schema.
- Create `src/tools/recordPerformance.ts` as a new tool in Milestone 3.
- Update `src/tools/createCreativeSprint.ts` to query performance records and return `performance_context` in the response.
- Update `src/services/database.ts` to include a `getTopPerformers(clientId, brandKitId)` query helper.
- Add `performance` to `src/schemas/brandKit.ts` as a derived read-only block populated from `PerformanceRecord`.
- Add `performanceRecord` RLS policy to Milestone 3 schema migrations.
- The brand kit update from a `top` performance record must go through the existing approval model (ADR-0005) before being committed.
