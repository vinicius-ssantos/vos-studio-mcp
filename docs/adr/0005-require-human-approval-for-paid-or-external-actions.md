# ADR-0005 — Require human approval for paid or external actions

Status: Amended  
Date: 2026-05-21  
Amended: 2026-05-21

## Context

VOS Studio MCP may trigger actions that spend credits, create billable API usage, publish content, send client-facing deliverables, or modify external systems.

Those actions should not happen accidentally through an agent instruction or ambiguous tool call.

The original decision required explicit per-action human approval. In practice, this creates a bottleneck: an agent building a full creative sprint would pause for approval on every individual generation job, eliminating the speed benefit of agent-driven workflows.

## Decision

Use a **sprint budget pre-authorization model** as the primary approval mechanism.

When a creative sprint is created or updated, the human operator sets an explicit budget ceiling:

```json
{
  "sprint_id": "spr_123",
  "budget": {
    "max_spend_usd": 40.00,
    "max_images": 30,
    "max_videos": 5,
    "alert_threshold_pct": 80
  }
}
```

Once the budget is pre-authorized, the agent may execute generation jobs autonomously as long as cumulative spend stays within the approved limits. The system must:

- Estimate cost before each job via `estimateCost` (ADR-0022).
- Block execution if the job would cause the sprint to exceed its budget ceiling.
- Emit an alert when spend crosses the `alert_threshold_pct`.
- Log every generation job and its actual cost to the audit log (ADR-0015).

Per-action approval is still required for:

- Any single job whose estimated cost exceeds 25% of the remaining sprint budget.
- Delivery actions that send files to external systems or clients.
- Any action that modifies data outside the current sprint scope.
- Jobs that would exceed the sprint budget ceiling — the agent must stop and request a budget increase, not silently skip.

## Alternatives considered

- **Fully autonomous execution**: rejected. No cost ceiling means unbounded spending risk.
- **Per-action approval for everything**: original decision. Correct in principle but creates friction that breaks agent workflows in practice.
- **Approval only for publishing**: too permissive for generation, which can be expensive per job.
- **Sprint budget pre-authorization with per-action fallback**: selected. Balances autonomy with control.

## Consequences

The agent can operate continuously within a sprint without stopping, which preserves the speed benefit of agent-driven production. The human retains control by setting the budget ceiling upfront and receiving alerts before it is exhausted.

Budget enforcement must happen at the service layer, not only at the tool layer, so it cannot be bypassed by a tool misconfiguration.

## Impact on VOS Studio MCP

Sprint schema must include a `budget` object with ceiling fields and a running `spent` tracker.

The `costEstimator` service must be called before every generation job and must compare estimated cost against remaining budget before enqueuing.

Tools must return `budget_status` in every generation response:

```json
{
  "job_id": "job_456",
  "status": "queued",
  "budget_status": {
    "approved_usd": 40.00,
    "spent_usd": 18.50,
    "remaining_usd": 21.50,
    "alert": false
  }
}
```

The `approval_token` mechanism from the original ADR remains for the per-action fallback cases listed above.
