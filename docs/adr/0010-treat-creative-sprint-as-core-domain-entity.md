# ADR-0010 — Treat the Creative Sprint as the core domain entity

Status: Accepted  
Date: 2026-05-21

## Context

VOS Studio's offer is centered on creative production packages, especially creative sprints for ads.

The MCP needs a domain model that matches how the agency sells, produces, reviews, and delivers work.

## Decision

Treat `CreativeSprint` as the core operational entity.

A sprint should connect:

- Client
- Brand kit
- Product or offer
- Campaign objective
- Angles
- Hooks
- Prompts
- Assets
- QA results
- Delivery pack
- Costs and approvals

## Alternatives considered

- Asset-first model: too focused on files instead of business workflow.
- Provider-job-first model: too tied to generation tools.
- CreativeSprint-first model: best fit for the agency offer.

## Consequences

The system aligns with how VOS Studio sells and delivers value.

The tradeoff is that low-level provider jobs must be mapped back to a sprint.

## Impact on VOS Studio MCP

Most tools should accept or return a `sprint_id`.

The first complete workflow should be:

```text
briefing → brand kit → creative sprint → dashboard pack → asset registration → QA → delivery
```
