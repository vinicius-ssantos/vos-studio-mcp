# ADR-0024 — Brand kit entity specification

Status: Accepted  
Date: 2026-05-21

## Context

The brand kit is referenced throughout the system — in client creation, creative sprints (ADR-0010), prompt packs, dashboard packs, QA, and delivery. Despite being the most critical input to creative quality, no decision has defined what a brand kit actually contains.

Without a canonical specification, each tool will interpret "brand kit" differently. A prompt pack tool may include color information that an asset registration tool ignores. A QA tool cannot check brand consistency without knowing what brand constraints exist. The system cannot generate useful prompts without a structured brand reference.

For a performance creative agency, the brand kit is also the mechanism that prevents creative drift across campaigns, clients, and agents. It is not a mood board — it is a set of constraints and references that shape every generation decision.

## Decision

The brand kit is a versioned entity with the following canonical structure:

```typescript
interface BrandKit {
  id: string;
  clientId: string;
  version: string;              // e.g. "v1", "v2-summer-refresh"
  name: string;
  status: 'active' | 'archived';

  identity: {
    brandName: string;
    tagline?: string;
    voice: string[];            // e.g. ["bold", "direct", "irreverent"]
    tone: string[];             // e.g. ["confident", "warm", "urgent"]
    targetAudience: string;
    positioning: string;        // one-sentence brand positioning
  };

  visual: {
    primaryColors: string[];    // hex values
    secondaryColors: string[];
    fonts: string[];
    logoRef?: AssetReference;   // stored externally per ADR-0008
    styleKeywords: string[];    // e.g. ["dark", "premium", "minimalist"]
    visualReferences: AssetReference[];
  };

  restrictions: {
    forbiddenElements: string[];    // e.g. ["competitor logos", "red backgrounds"]
    forbiddenPhrases: string[];
    contentWarnings: string[];      // e.g. ["no children", "no alcohol"]
    platformRules: Record<string, string[]>; // platform-specific constraints
  };

  performance: {
    provenAngles: string[];         // angles that have worked historically
    provenHooks: string[];          // hooks with confirmed performance
    failedApproaches: string[];     // documented failures to avoid repeating
    topAssetRefs: AssetReference[]; // references to best-performing past assets
  };

  createdAt: string;
  updatedAt: string;
}
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

- Create `src/schemas/brandKit.ts` with the full Zod schema derived from the interface above.
- The `save_brand_kit` tool must validate the full schema on creation and version on update.
- All prompt generation tools must accept `brandKitId` and `brandKitVersion` and use the brand kit to constrain output.
- Dashboard packs (Milestone 2) must include a section derived from `restrictions` as a checklist item.
- QA tools must use `restrictions.forbiddenElements` and `restrictions.forbiddenPhrases` as automated rejection criteria.
- The `performance` block must be updated by the performance feedback tool (ADR-0025) — it must not be editable directly via `save_brand_kit` to prevent manual data contamination.
