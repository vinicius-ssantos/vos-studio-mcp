# ADR-0001 — Use TypeScript as the primary language

Status: Accepted  
Date: 2026-05-21

## Context

VOS Studio MCP will be the operational server for VOS Studio's creative workflows. It needs to support MCP tools, schemas, authentication, provider integrations, storage, jobs, clients, brand kits, creative sprints, asset registration, QA, and delivery workflows.

The project will also be developed with the help of coding agents such as Claude Code and Codex. The codebase should therefore be typed, readable, modular, and easy for agents to navigate safely.

## Decision

Use TypeScript and Node.js as the primary language/runtime for the MCP server.

Python may be introduced later for auxiliary scripts, experiments, image analysis, batch processing, or ML-specific workflows, but it will not be the primary language of the MCP server.

## Alternatives considered

- Python: strong ecosystem for AI and scripting, but less ideal as the main web-first backend for this project.
- TypeScript: best balance for MCP server implementation, typed schemas, web integrations, deployment, and agent-assisted maintenance.
- Go or Rust: strong performance and reliability, but higher initial complexity for this MVP.

## Consequences

TypeScript gives us typed schemas, a strong Node ecosystem, straightforward integration with web APIs, and a codebase that Claude/Codex can modify predictably.

The main tradeoff is depending on the Node ecosystem, but that is acceptable for a creative operations MVP.

## Impact on VOS Studio MCP

The initial project structure should use `src/`, `tools/`, `schemas/`, `services/`, and validation with Zod or an equivalent TypeScript schema library.

MCP tools should expose clear typed inputs and compact outputs to reduce token cost and improve reliability.
