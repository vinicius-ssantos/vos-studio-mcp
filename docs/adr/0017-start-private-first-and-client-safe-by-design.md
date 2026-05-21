# ADR-0017 — Start private-first and client-safe by design

Status: Accepted  
Date: 2026-05-21

## Context

VOS Studio MCP will contain agency strategy, client data, brand kits, prompts, creative decisions, provider usage, and potentially client deliverables.

This information should not be public by default.

## Decision

Build the project private-first and client-safe by design.

The repository, database, storage, logs, and generated outputs should assume confidential client data.

## Alternatives considered

- Public-first repository: rejected for strategy and client confidentiality.
- Public core with private config: possible later, but not for the MVP.
- Private-first: accepted.

## Consequences

This protects client and agency information.

The tradeoff is less public reuse and fewer open-source contribution benefits.

## Impact on VOS Studio MCP

Use private repositories, restricted storage, minimal logging of sensitive content, and explicit access controls before adding team or client-facing features.
