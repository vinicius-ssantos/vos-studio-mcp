# ADR-0020 — Database schema evolution and migration strategy

Status: Accepted  
Date: 2026-05-21

## Context

ADR-0007 decided that Postgres via Supabase will be the system of record. ADR-0013 requires that prompts and presets be versioned, and every generated asset must record which prompt and preset version produced it.

As the system evolves — new providers (ADR-0009), new sprint fields (ADR-0010), new budget controls (ADR-0012), new audit events (ADR-0015) — the database schema will change frequently. Without an explicit migration strategy, schema drift, broken deployments, and data loss become likely.

Running raw SQL against Supabase manually is not repeatable or auditable. A migration tool must be chosen before Milestone 3 work begins.

## Decision

Use **Drizzle ORM** with SQL migration files as the migration strategy for Postgres/Supabase.

Drizzle was chosen over Prisma because:
- It generates plain SQL migration files that can be reviewed, versioned in Git, and run directly against Supabase.
- It has no runtime query builder overhead in production if a direct Postgres client is preferred.
- Its schema definitions in TypeScript align well with the rest of the codebase (ADR-0001) and with Zod-based validation.

Migration files live in `db/migrations/`. Each migration has a sequential numeric prefix and a descriptive name (e.g. `0001_create_clients.sql`).

All schema changes — including adding columns, changing constraints, and creating indexes — must go through a migration file. No schema changes via the Supabase dashboard UI in production.

## Alternatives considered

- **Prisma Migrate**: strong tooling and type generation, but Prisma's migration history table and shadow database requirements add complexity in Supabase-hosted environments. Rejected in favor of Drizzle's lighter footprint.
- **Raw SQL managed manually**: gives full control but no tooling for tracking applied migrations. Rejected because it does not scale safely across environments and agents.
- **Flyway or Liquibase**: production-grade migration tools, but Java-based and mismatched with the TypeScript-first stack. Rejected.
- **Supabase dashboard UI**: suitable for exploration, not for repeatable production deployments. Rejected for production use.

## Consequences

All schema changes are code-reviewed via PRs before they are applied. This slows down exploratory schema work but prevents unreviewed changes from reaching production.

The `db/migrations/` directory becomes a critical path artifact. Migration files, once merged and applied to production, must not be modified — only new migrations can alter the schema.

Drizzle will generate TypeScript types from the schema, which tools and services can import directly, keeping the type system consistent from DB to MCP output.

## Impact on VOS Studio MCP

- Add `drizzle-orm` and `drizzle-kit` as dependencies in Milestone 3.
- Create `db/schema.ts` as the single source of truth for table definitions.
- Create `db/migrations/` for generated SQL files.
- Add a `db:migrate` script to `package.json` for applying migrations in CI and deployment.
- The `.env.example` must include the `DATABASE_URL` variable for Supabase Postgres connection string.
- Local development uses the same Postgres schema via a local Supabase instance or a Docker Postgres container.
