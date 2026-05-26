# ADR-0038 — BrandKit Asset Lock (Campaign Visual System v2)

**Status:** Accepted  
**Date:** 2026-05-26  
**Related issues:** #52, #56

---

## Context

The existing `BrandKit` entity captures `identity`, `visual`, `restrictions`,
and `performance_memory` as JSONB documents.  This is sufficient for basic
brand alignment, but it does not express the campaign-level visual constraints
that VOS uses in production:

- **Registers**: which dominant/secondary visual registers define the campaign,
  and which are forbidden.
- **Materials**: surfaces and props that are allowed or forbidden.
- **Environments**: settings and locations that are allowed or forbidden.
- **Text policy**: rules for on-screen text (when it is allowed, in which shots).
- **Endcard policy**: what the endcard must contain and how long it runs.
- **Reference assets**: specific approved assets that operators must treat as
  creative anchors.

Without this, the blueprint service cannot enforce campaign-level visual
consistency beyond basic color palette, and operators must rely on undocumented
knowledge to execute correctly.

---

## Decision

Add an `asset_lock` JSONB column to the `brand_kits` table.

### Schema

The `asset_lock` document has the following fields (all optional):

| Field | Type | Description |
|-------|------|-------------|
| `dominant_register` | string | Primary visual register (e.g. "bold product-forward") |
| `secondary_register` | string | Supporting register (e.g. "warm lifestyle") |
| `forbidden_register` | list[str] | Registers explicitly forbidden |
| `allowed_materials` | list[str] | Materials/surfaces allowed |
| `forbidden_materials` | list[str] | Materials/surfaces forbidden |
| `allowed_environments` | list[str] | Settings allowed |
| `forbidden_environments` | list[str] | Settings forbidden |
| `text_policy` | string | On-screen text rules |
| `endcard_policy` | string | Endcard composition and timing requirements |
| `reference_asset_ids` | list[str] | Asset IDs of approved reference assets |

### Integration

- `save_brand_kit` accepts an optional `asset_lock` field.
- `prepare_video_blueprint` includes `forbidden_register`, `forbidden_materials`,
  and `forbidden_environments` in the negative prompts list.
- `prepare_execution_pack` exposes `asset_lock` constraints in operator guidance.

### Backward Compatibility

The `asset_lock` column is nullable.  Existing brand kits have `asset_lock = NULL`,
which is treated as "no asset lock" — all existing behavior is preserved.

---

## Consequences

**Good:**
- Blueprint negative prompts now reflect the full campaign visual fence.
- Operators receive explicit allowed/forbidden guidance in execution packs.
- `save_brand_kit` can capture the complete campaign visual system in one call.
- No breaking changes to existing brand kit data or tool contracts.

**Trade-off:**
- Asset lock fields are untyped at the DB level (JSONB).
  Pydantic validates at the API boundary; invalid documents pass through if
  saved directly to the DB.
