# ADR-0018 — Use incremental PR-based development with coding agents

Status: Accepted  
Date: 2026-05-21

## Context

The project will be developed with Claude Code, Codex, and other coding agents. Large autonomous edits can be hard to review and may introduce unrelated changes.

## Decision

Use incremental PR-based development.

Each agent task should target a small branch and PR with a clear slice of work.

## Alternatives considered

- Direct commits to main: rejected.
- Large multi-feature branches: rejected.
- Small focused PRs: accepted.

## Consequences

This improves reviewability, rollback, and agent safety.

The tradeoff is more branch and PR overhead, but this is acceptable for a foundational system.

## Impact on VOS Studio MCP

Preferred flow:

```text
create branch → implement one slice → run checks → open PR → review → merge
```

Agent instructions should reference ADRs before implementing architectural changes.
