# ADR-0011 — Keep MCP tool outputs compact and structured

Status: Accepted  
Date: 2026-05-21

## Context

Large MCP responses increase token usage and make agent reasoning less reliable. Full prompts, logs, raw provider payloads, and long asset lists can quickly bloat context.

## Decision

MCP tools should return compact, structured outputs by default.

They should include:

- status
- IDs
- short summary
- next recommended action
- relevant links or references
- warnings or blockers

Detailed content should be stored in the database or storage and fetched only when needed.

## Alternatives considered

- Return everything: simple, but expensive and noisy.
- Return only IDs: too opaque.
- Return compact summaries plus references: accepted.

## Consequences

This reduces token cost and improves agent reliability.

The tradeoff is that additional tool calls may be needed to inspect full details.

## Impact on VOS Studio MCP

Default tool responses should look like:

```json
{
  "status": "created",
  "sprint_id": "spr_123",
  "summary": "Sprint created with 5 angles, 10 hooks and 6 prompt packs.",
  "next_action": "prepare_dashboard_pack"
}
```
