# ADR-0013 — Keep prompts and presets versioned

Status: Accepted  
Date: 2026-05-21

## Context

VOS Studio's creative quality will depend on repeatable prompt patterns, provider settings, visual presets, brand constraints, and QA criteria.

If prompts change without versioning, it becomes difficult to understand which process produced each asset.

## Decision

Prompts, presets, and creative templates should be versioned.

Each generated asset should store the prompt version and preset version used to create it.

## Alternatives considered

- Store only final prompts: insufficient for repeatability.
- Keep prompts in code only: hard to update operationally.
- Version prompts and presets: accepted.

## Consequences

This improves repeatability, QA, and learning across client work.

The tradeoff is extra structure around prompt management.

## Impact on VOS Studio MCP

Entities should include fields such as:

```json
{
  "prompt_version": "skincare-packshot-v1",
  "preset_version": "premium-dark-v1"
}
```
