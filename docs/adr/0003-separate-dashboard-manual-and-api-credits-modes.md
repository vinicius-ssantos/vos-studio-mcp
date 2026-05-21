# ADR-0003 — Separate dashboard_manual and api_credits modes

Status: Accepted  
Date: 2026-05-21

## Context

VOS Studio will use tools such as Higgsfield, Freepik, and Magnific.

Some paid-plan benefits are meant for human use inside dashboards, while APIs, MCPs, and CLIs usually use credits, API billing, or separate usage limits.

## Decision

Every generation workflow must explicitly choose one of two modes:

- `dashboard_manual`: the MCP prepares prompts, presets, parameters, and checklists for human execution inside the provider dashboard.
- `api_credits`: the MCP executes through an official API, MCP, or CLI path, using credits or API billing.

## Alternatives considered

- Automate dashboards through browser control: rejected due to account, terms, and operational risk.
- Use APIs for everything: rejected because exploration and iteration could become expensive.
- Use only manual dashboards: rejected because it reduces traceability and operational scale.

## Consequences

This keeps the agency workflow legal, auditable, and cost-aware.

Manual mode supports human dashboard execution. API mode supports controlled automation.

## Impact on VOS Studio MCP

Sprints, jobs, and assets must store a `mode` field.

Tools that run in `api_credits` mode must estimate cost and require approval before executing.
