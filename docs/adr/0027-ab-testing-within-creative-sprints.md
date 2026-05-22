# ADR-0027 — A/B testing within creative sprints

Status: Amended  
Date: 2026-05-21  
Amended: 2026-05-22

## Context

ADR-0025 introduced the performance feedback loop: assets are linked to performance records, which inform future sprints. This creates reactive learning — the system learns from what happened.

The next step is proactive learning: structuring experiments within a sprint to test specific creative hypotheses deliberately. Instead of producing a batch of assets and waiting to see which performs better by chance, the agency can define variants upfront — "urgency hook vs social proof hook for this audience" — and track results against a defined hypothesis.

Without a structured A/B testing framework, this experimentation happens informally in spreadsheets or verbal notes. The system cannot aggregate learnings, detect statistically significant differences, or recommend the winning variant for future sprints.

For a performance creative agency, the ability to run structured creative experiments and accumulate their results is a significant operational and competitive advantage.

## Decision

Introduce a `CreativeVariant` entity nested within a `CreativeSprint`.

A sprint may contain one or more variant groups. Each group tests a specific creative hypothesis with two or more variants:

```python
@dataclass
class VariantGroup:
    id: str
    sprint_id: str
    hypothesis: str           # e.g. "urgency hook outperforms social proof for cold audiences"
    variable: str             # what is being tested: "hook_type", "visual_style", "cta", etc.
    variants: list["Variant"]
    status: Literal["running", "concluded", "inconclusive"]
    winner_variant_id: str | None
    concluded_at: str | None

@dataclass
class Variant:
    id: str
    group_id: str
    label: str                # e.g. "urgency", "social_proof"
    description: str
    prompt_version: str       # per ADR-0013
    preset_version: str
    asset_ids: list[str]      # assets generated for this variant
    performance_record_ids: list[str]  # linked performance data (ADR-0025)
```

### Workflow

1. When creating a sprint, the operator optionally defines one or more `VariantGroup` objects with a hypothesis and variants.
2. The MCP generates assets for each variant using the corresponding `prompt_version` and `preset_version`.
3. After the campaign runs, `record_performance` links results to the specific `variant_id`, not just the `asset_id`.
4. A `conclude_variant_test` tool compares performance across variants and marks a winner based on the primary metric defined at group creation (e.g. CTR, ROAS, thumbStopRate).
5. The winning variant's elements are proposed as additions to the brand kit's `performance.proven_angles` or `performance.proven_hooks` (ADR-0024), subject to approval.

### Statistical significance

The system does not compute statistical significance automatically in the initial implementation — this requires sample sizes that early sprints may not reach. Instead, the `conclude_variant_test` tool surfaces the raw metric comparison and requires the operator to confirm the winner. Statistical significance calculation is deferred to Milestone 6 when performance data volume is sufficient.

## Alternatives considered

- **Informal A/B testing via naming conventions**: operators name assets "variant-a-urgency" and compare manually. Rejected — unqueryable and cannot feed back into the brand kit systematically.
- **Full statistical framework from the start**: correct long-term but requires large sample sizes to be meaningful and adds implementation complexity before there is data to use it. Rejected for the initial implementation.
- **Structured variants with manual winner selection**: selected. Immediately useful, queryable, and extensible to automated significance testing later.

## Consequences

`VariantGroup` and `Variant` become new entities in the database schema, requiring Alembic migrations and RLS policies (ADR-0023).

The performance feedback loop (ADR-0025) is enriched: `PerformanceRecord` gains a `variant_id` foreign key. This is backwards-compatible — records without a `variant_id` are treated as unstructured performance data.

Sprints that use variant groups produce more assets per sprint (one per variant), which increases generation cost. The budget pre-authorization model (ADR-0005) must account for the total cost across all variants.

## Implementation status

| Component | Status |
|-----------|--------|
| `VariantGroup` + `Variant` ORM models in `db/models.py` | ✅ Implemented |
| `Asset.variant_id` FK (optional) | ✅ Implemented |
| Migration `0004_add_variant_tables.py` (RLS included) | ✅ Implemented |
| `schemas/variant.py` — `ConcludeVariantTestInput/Response` | ✅ Implemented |
| `services/variant_service.py` — `conclude_variant_test` | ✅ Implemented |
| `tools/conclude_variant_test.py` — MCP tool | ✅ Implemented |
| Unit tests — `tests/services/test_variant_service.py` | ✅ Implemented |
| `create_creative_sprint` — accept variant group definitions | ✅ Implemented |
| `record_performance` — optional `variant_id` | ✅ Implemented |

## Impact on VOS Studio MCP

- `db/models.py` — `VariantGroup`, `Variant` models; `Asset.variant_id` FK.
- `db/migrations/versions/0004_add_variant_tables.py` — tables + RLS policies scoped via sprint → client.
- `src/vos_studio_mcp/schemas/variant.py` — `ConcludeVariantTestInput`, `ConcludeVariantTestResponse`.
- `src/vos_studio_mcp/services/variant_service.py` — `conclude_variant_test` service.
- `src/vos_studio_mcp/tools/conclude_variant_test.py` — MCP tool registered in `tools/__init__.py`.
