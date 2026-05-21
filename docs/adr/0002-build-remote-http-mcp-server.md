# ADR-0002 — Build a remote HTTP MCP server

Status: Accepted  
Date: 2026-05-21

## Context

The MCP should be usable from ChatGPT, Claude, Codex, and potentially other clients. A local stdio server is useful during development, but the real agency workflow needs a secure remote endpoint that can be connected to multiple agents.

## Decision

Design VOS Studio MCP as a remote HTTP MCP server from the beginning.

Local stdio can be supported for development, but the main production target is a secure HTTPS endpoint such as:

```text
https://mcp.vosstudio.com/mcp
```

## Alternatives considered

- Local stdio only: simple, but limits production usage.
- CLI scripts only: fast to prototype, but not a shared operational layer.
- Remote HTTP MCP: better for ChatGPT, team workflows, logs, deployment, and long-term operations.

## Consequences

This enables real usage across agents and future team members.

The tradeoff is that we must handle authentication, secrets, rate limits, logs, deployment, and operational security from the start.

## Impact on VOS Studio MCP

The server must separate transport, tools, services, providers, persistence, and authentication concerns.
