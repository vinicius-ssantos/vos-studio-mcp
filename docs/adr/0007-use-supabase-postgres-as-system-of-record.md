# ADR-0007 — Use Supabase/Postgres as the system of record

Status: Accepted  
Date: 2026-05-21

## Context

The MCP needs persistent records for clients, brand kits, creative sprints, jobs, assets, prompts, costs, approvals, and delivery packs.

The database should be easy to inspect, migrate, and connect to future dashboards.

## Decision

Use Supabase/Postgres as the primary system of record.

## Alternatives considered

- JSON files: simple, but fragile and hard to query.
- SQLite: good for local development, but weaker for remote multi-user workflows.
- Supabase/Postgres: strong default for a production-ready MVP with auth, APIs, and relational data.

## Consequences

Postgres gives structure, queryability, relational integrity, and a path to dashboards.

The tradeoff is earlier database setup and migration management.

## Impact on VOS Studio MCP

Domain entities should be modeled around clients, brand kits, sprints, jobs, assets, prompts, approvals, and deliveries.

Local development may use a lightweight database only if it remains compatible with the Postgres schema.
