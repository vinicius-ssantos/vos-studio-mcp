# ADR-0005 — Require human approval for paid or external actions

Status: Accepted  
Date: 2026-05-21

## Context

VOS Studio MCP may trigger actions that spend credits, create billable API usage, publish content, send client-facing deliverables, or modify external systems.

Those actions should not happen accidentally through an agent instruction or ambiguous tool call.

## Decision

Any action that spends credits, creates API billing, publishes content, sends client-facing files, or modifies external systems must require explicit human approval.

## Alternatives considered

- Fully autonomous execution: rejected for cost and client-safety reasons.
- Approval only for publishing: rejected because generation itself can be expensive.
- Explicit approval for paid/external actions: accepted.

## Consequences

This prevents accidental spending and protects client-facing operations.

The tradeoff is extra friction, but this is acceptable for a premium creative agency workflow.

## Impact on VOS Studio MCP

Paid/external tools must expose fields such as:

```json
{
  "requires_approval": true,
  "estimated_cost": "...",
  "approval_token": "..."
}
```

Execution should only proceed after approval is explicit and auditable.
