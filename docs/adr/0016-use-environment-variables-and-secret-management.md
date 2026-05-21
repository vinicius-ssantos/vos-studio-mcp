# ADR-0016 — Use environment variables and secret management for credentials

Status: Accepted  
Date: 2026-05-21

## Context

The project will need credentials for providers, databases, storage, and possibly OAuth. Secrets must not be committed to the repository or exposed in MCP responses.

## Decision

Use environment variables and platform secret management for all credentials.

The repository should include `.env.example` but never real secrets.

## Alternatives considered

- Hardcode credentials: rejected.
- Store secrets in source-controlled config files: rejected.
- Use environment variables and managed secrets: accepted.

## Consequences

This is safer and compatible with modern deployment platforms.

The tradeoff is that local setup requires explicit environment configuration.

## Impact on VOS Studio MCP

All provider clients must read credentials from environment variables or a secret manager.

Logs and tool outputs must never expose API keys, tokens, cookies, or credentials.
