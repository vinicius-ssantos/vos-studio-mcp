# ADR-0024 — Brand kit entity specification

Status: Accepted  
Date: 2026-05-21

## Context

The brand kit is referenced throughout the system — in client creation, creative sprints (ADR-0010), prompt packs, dashboard packs, QA, and delivery. Despite being the most critical input to creative quality, no decision has defined what a brand kit actually contains.

Without a canonical specification, each tool will interpret "brand kit" differently. A prompt pack tool may include color information that an asset registration tool ignores. A QA tool cannot check brand consistency without knowing what brand constraints exist. The system cannot generate useful prompts without a structured brand reference.

For a performance creative agency, the brand kit is also the mechanism that prevents creative drift across campaigns, clients, and agents. It is not a mood board — it is a set of constraints and references that shape every generation decision.

## Decision

The brand kit is a versioned entity with the following canonical structure:

```python
from typing import Literal
from pydantic import BaseModel, Field


class BrandIdentity(BaseModel):
    brand_name: str
    tagline: str | None = None
    voice: list[str] = Field(default_factory=list)
    tone: list[str] = Field(default_factory=list)
    target_audience: str
    positioning: str


class BrandVisualSystem(BaseModel):
    primary_colors: list[str] = Field(default_factory=list)  # hex values
    secondary_colors: list[str] = Field(default_factory=list)
    fonts: list[str] = Field(default_factory=list)
    logo_ref: "AssetReference | None" = None
    style_keywords: list[str] = Field(default_factory=list)
    visual_references: list["AssetReference"] = Field(default_factory=list)


class BrandRestrictions(BaseModel):
    forbidden_elements: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    content_warnings: list[str] = Field(default_factory=list)
    platform_rules: dict[str, list[str]] = Field(default_factory=dict)


class BrandPerformanceMemory(BaseModel):
    proven_angles: list[str] = Field(default_factory=list)
    proven_hooks: list[str] = Field(default_factory=list)
    failed_approaches: list[str] = Field(default_factory=list)
    top_asset_refs: list["AssetReference"] = Field(default_factory=list)


class BrandKit(BaseModel):
    id: str
    client_id: str
    version: str
    name: str
    status: Literal["active", "archived"] = "active"
    identity: BrandIdentity
    visual: BrandVisualSystem
    restrictions: BrandRestrictions
    performance: BrandPerformanceMemory = Field(default_factory=BrandPerformanceMemory)
    created_at: str
    updated_at: str
```


The `performance` block is seeded empty and populated over time as `PerformanceRecord` entries are linked to the brand kit (ADR-0025). This is the mechanism through which the system accumulates institutional creative knowledge.

Brand kits are versioned. A new version is created when significant changes occur (visual refresh, repositioning, new platform rules). Sprints reference a specific `brandKitVersion` so that historical sprints remain reproducible (ADR-0013).

## Alternatives considered

- **Unstructured brand kit as free-text blob**: simple to implement, impossible to use programmatically in prompt generation or QA. Rejected.
- **Brand kit as external document reference only**: avoids specifying a schema but gives tools nothing to work with. Rejected.
- **Minimal brand kit (name + colors only)**: not enough to differentiate client output or enforce creative constraints. Rejected.
- **Full specification as above**: accepted. More complex upfront but enables programmatic prompt enrichment, brand-consistent QA, and performance learning.

## Consequences

The brand kit becomes the richest input entity in the system. Creating a useful brand kit requires real effort from the operator or client — it cannot be auto-generated. Onboarding a new client now includes a brand kit creation step before any sprint can begin.

Tools that generate prompts or prepare dashboard packs must consume the brand kit and incorporate its constraints into every output. A prompt pack tool that ignores the brand kit's `restrictions` block is producing incorrect output.

The `performance` block creates a dependency on ADR-0025: the brand kit specification is complete only when the performance feedback loop is implemented.

## Impact on VOS Studio MCP

- Create `src/vos_studio_mcp/schemas/brand_kit.py` with the full Pydantic schema derived from the model above.
- The `save_brand_kit` tool must validate the full schema on creation and version on update.
- All prompt generation tools must accept `brand_kit_id` and `brand_kit_version` and use the brand kit to constrain output.
- Dashboard packs (Milestone 2) must include a section derived from `restrictions` as a checklist item.
- QA tools must use `restrictions.forbiddenElements` and `restrictions.forbiddenPhrases` as automated rejection criteria.
- The `performance` block must be updated by the performance feedback tool (ADR-0025) — it must not be editable directly via `save_brand_kit` to prevent manual data contamination.
