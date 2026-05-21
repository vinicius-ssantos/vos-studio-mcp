# ADR-0009 — Use provider adapters for Higgsfield, Freepik, and Magnific

Status: Accepted  
Date: 2026-05-21

## Context

The agency may use multiple creative providers. Each provider has different APIs, dashboards, MCP capabilities, billing rules, models, limits, and output formats.

Hardcoding provider logic inside MCP tools would make the codebase brittle.

## Decision

Create provider adapters behind a common internal interface.

Initial adapters may include:

- Higgsfield
- Freepik
- Magnific
- Manual dashboard execution

## Alternatives considered

- Hardcode provider calls inside each tool: fast but hard to maintain.
- Use one universal provider abstraction from day one: too abstract too early.
- Use thin provider adapters with shared conventions: accepted.

## Consequences

This improves maintainability and makes it easier to add or replace providers.

The tradeoff is a small upfront abstraction cost.

## Impact on VOS Studio MCP

Tools should call internal services such as `providers.higgsfield`, `providers.magnific`, or `providers.manualDashboard`, not raw provider APIs directly.
