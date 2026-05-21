# ADR-0012 — Use explicit cost budgets and generation limits

Status: Accepted  
Date: 2026-05-21

## Context

Image generation can be manageable, but video generation and automated API usage can become expensive quickly.

The agency needs cost visibility before running generation jobs.

## Decision

Every sprint and provider job should support explicit budgets and generation limits.

Budgets may include:

- max credits
- max API spend
- max images
- max videos
- max retries
- max duration or resolution
- max provider-specific cost

## Alternatives considered

- No budgets during MVP: rejected due to cost risk.
- Manual tracking only: insufficient for automation.
- Built-in budget fields and checks: accepted.

## Consequences

This reduces surprise costs and improves client profitability.

The tradeoff is extra metadata and budget-checking logic.

## Impact on VOS Studio MCP

Generation tools must estimate cost when possible and block execution when the job exceeds budget or lacks approval.
