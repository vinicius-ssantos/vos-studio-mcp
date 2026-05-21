# ADR-0006 — Use workflow-oriented tools to reduce token cost

Status: Accepted  
Date: 2026-05-21

## Context

MCP tool descriptions, schemas, calls, responses, and intermediate logs all consume model context. A large number of tiny tools can make the agent slower, more expensive, and less reliable.

## Decision

Prefer fewer workflow-oriented tools over many micro-tools.

Examples of preferred tools:

- `create_creative_sprint`
- `prepare_dashboard_pack`
- `register_manual_asset`
- `estimate_generation_cost`
- `run_approved_generation`
- `create_delivery_pack`

## Alternatives considered

- Many granular tools: flexible but costly in tokens and harder for agents to sequence.
- One giant tool: too opaque and hard to test.
- A small set of workflow tools: best initial balance.

## Consequences

The agent gets fewer choices and clearer workflows.

The tradeoff is that each tool must be well-designed and may contain multiple internal steps.

## Impact on VOS Studio MCP

Tool names should map to business workflows, not low-level implementation steps.

Tools should return compact summaries, IDs, next actions, and links instead of full internal logs.
