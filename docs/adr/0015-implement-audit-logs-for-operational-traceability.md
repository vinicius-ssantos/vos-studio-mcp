# ADR-0015 — Implement audit logs for operational traceability

Status: Accepted  
Date: 2026-05-21

## Context

The MCP will coordinate client work, provider usage, approvals, prompts, assets, and delivery packages. The agency needs to know what happened, when, why, and under which approval.

## Decision

Implement audit logs for important actions.

Audit events should include:

- actor
- action
- timestamp
- entity type and ID
- provider
- mode
- cost estimate
- approval status
- result or failure reason

## Alternatives considered

- No audit logs in MVP: rejected because cost and client workflows need traceability.
- Raw logs only: hard to query and connect to business entities.
- Structured audit events: accepted.

## Consequences

This improves accountability, debugging, and client operations.

The tradeoff is extra persistence and event design.

## Impact on VOS Studio MCP

Every paid, external, delivery, approval, or asset-changing action should write an audit event.
