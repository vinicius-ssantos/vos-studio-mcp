# ADR-0037 — Asset Stage and Lineage Model

**Status:** Accepted  
**Date:** 2026-05-26  
**Related issues:** #53, #55

---

## Context

The `Asset` model previously captured only technical metadata about an asset
(provider, URLs, dimensions, performance) with no domain classification.
This meant the server had no way to express:

- Which VOS production stage an asset belongs to (anchor image, character sheet, video, etc.)
- Whether an asset was generated, manually registered, or upscaled
- Whether an asset derives from another (repair variant, upscale source)
- Whether an asset has been approved as a reference for future sprints
- Whether an asset is a final deliverable

Without this metadata, the system behaves as a generic job/asset registry rather
than a stage-aware creative system.

---

## Decision

Add five fields to the `assets` table:

### asset_stage

Classifies the asset by its VOS production stage.

| Value | Description |
|-------|-------------|
| `stage_0` | Anchor image — the base reference for the campaign |
| `stage_a` | Character sheet — talent/character reference images |
| `stage_b` | Storyboard — pre-visualization frames |
| `stage_c` | Video — final video output |
| `repair` | Repair variant — a corrected version of another asset |
| `final` | Final delivery — the sprint's approved deliverable |

Nullable for backward compatibility (existing assets have no stage).

### asset_kind

Describes how the asset was produced.

| Value | Description |
|-------|-------------|
| `generated` | API-generated via a provider (Higgsfield, Freepik, etc.) |
| `manual` | Manually registered via dashboard (`register_manual_asset`) |
| `upscaled` | Upscaled/enhanced via Magnific or similar |

Default: `manual` (preserves intent for existing manual assets).

### source_asset_id

Self-referencing FK to `assets.id` (`ON DELETE SET NULL`).
Represents the asset that this asset was derived from.

Use cases:
- A repair variant's `source_asset_id` points to the original rejected asset
- An upscaled asset's `source_asset_id` points to the source frame
- `NULL` for original/independent assets

### approved_as_reference

Boolean, default `false`.  Set to `true` by QA when the asset is approved
for use as a reference asset in future sprints.  Surfaces in
`list_sprint_assets` output.

### is_final_delivery

Boolean, default `false`.  Set to `true` when the asset is the final
deliverable for its sprint.  A sprint may have exactly one final delivery
asset per campaign.

---

## Consequences

**Good:**
- Sprint asset listings expose full VOS production context per asset.
- `register_manual_asset` can classify stage/kind at registration time.
- API-generated assets can be classified in `generation_service` (stage_c for Higgsfield).
- Lineage traversal is possible via `source_asset_id`.
- `approved_as_reference=true` assets can be surfaced as reference context.

**Trade-off:**
- Stage/kind fields are optional at registration — callers must opt in.
- No uniqueness constraint on `is_final_delivery` to avoid migration complexity;
  application-layer logic enforces "one final per sprint" when needed.

---

## Migration

Migration `0013_add_asset_stage_kind_lineage.py` adds all five columns.
Existing assets default to `asset_kind="manual"`, `asset_stage=NULL`,
`source_asset_id=NULL`, `approved_as_reference=false`, `is_final_delivery=false`.
