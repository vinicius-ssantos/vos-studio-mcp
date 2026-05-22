# ADR-0029 — Cross-client prompt library

Status: Amended  
Date: 2026-05-21  
Amended: 2026-05-22

## Context

ADR-0013 requires that prompts and presets be versioned per client. ADR-0025 links performance records to specific prompt versions, allowing the system to learn which prompts produced better-performing assets for a given client.

This per-client learning is valuable, but it misses an opportunity. The agency works across multiple clients in similar industries, with similar product types and campaign objectives. A prompt structure that consistently drives CTR for skincare e-commerce brands is likely valuable for other skincare clients — even if the brand-specific content differs. Currently, this institutional knowledge lives only in individual brand kits and is invisible across clients.

A cross-client prompt library would allow the agency to accumulate, anonymize, and reuse prompt patterns that have demonstrated performance value. Over time this becomes a significant competitive asset: the agency's collective creative intelligence, encoded in a searchable library, inaccessible to competitors who start each client engagement from scratch.

## Decision

Introduce a `PromptTemplate` entity that represents an anonymized, reusable prompt pattern — distinct from client-specific prompt versions.

```python
@dataclass
class PromptTemplate:
    id: str
    name: str
    description: str

    # Classification
    industry: list[str]       # e.g. ["skincare", "e-commerce"]
    format: list[str]         # e.g. ["static_image", "video_ad", "ugc"]
    objective: list[str]      # e.g. ["awareness", "conversion", "retargeting"]
    platform: list[str]       # e.g. ["meta", "tiktok", "google"]

    # Template content
    prompt_template: str      # prompt with {{placeholders}} for brand-specific values
    negative_prompt_template: str | None
    preset_recommendations: list[str]   # preset version IDs that work well with this template

    # Performance signal
    avg_ctr: float | None          # aggregated across clients, null until enough data
    avg_roas: float | None
    usage_count: int               # how many sprints have used this template
    performance_tier: Literal["proven", "experimental", "deprecated"]

    # Provenance
    derived_from_sprint_ids: list[str]   # source sprints (internal reference, not exposed)
    contributed_by: str                  # agency operator who approved the template
    approved_at: str
    created_at: str
    updated_at: str
```

### Privacy model

`PromptTemplate` contains **no client-identifying information**. Brand names, product names, specific visual references, and any other client-identifiable content must be replaced with `{{placeholders}}` before a prompt is promoted to the library.

Promotion is a manual, human-approved action — not automatic. A `promote_to_library` tool takes a specific `prompt_version` from a client sprint and guides the operator through the anonymization process, requiring explicit confirmation before saving to the library.

### Usage in sprint creation

When `create_creative_sprint` is called, the tool optionally queries the prompt library for templates that match the sprint's `industry`, `format`, `objective`, and `platform`. Matching templates are returned in `sprint_context` alongside the client's own performance context (ADR-0025):

```json
{
  "sprint_id": "spr_789",
  "performance_context": { ... },
  "library_suggestions": [
    {
      "template_id": "tpl_001",
      "name": "Urgency + scarcity for conversion",
      "performance_tier": "proven",
      "avg_ctr": 0.038,
      "prompt_preview": "Show {{product}} with limited stock messaging..."
    }
  ],
  "next_action": "prepare_dashboard_pack"
}
```

The operator or agent uses the template as a starting point, filling in the `{{placeholders}}` with client-specific content. The resulting filled prompt is saved as a new `prompt_version` for the client — the template itself is never modified by individual sprint use.

### Access control

`PromptTemplate` records are **not client-scoped**. They are agency-wide resources visible to all authenticated sessions. The RLS model (ADR-0023) does not restrict access to the library — but write access (promotion, deprecation) is restricted to agency operator roles, not client-level tokens.

## Alternatives considered

- **Per-client prompt sharing only**: each client's brand kit accumulates its own proven prompts (ADR-0024 and ADR-0025). Useful but siloed. Rejected as the only mechanism.
- **Fully automatic promotion**: high-performing prompts are automatically added to the library. Rejected — risks leaking client-specific content if the anonymization step is skipped.
- **External prompt marketplace**: sharing prompt templates outside the agency. Out of scope for this project. Rejected.
- **Manual library with human-approved promotion**: selected. Ensures privacy, maintains quality, and creates a deliberate agency knowledge curation practice.

## Consequences

The prompt library is only as valuable as the volume and quality of prompts contributed to it. In early sprints (Milestone 2–3), the library will be empty. Adoption depends on operators using the `promote_to_library` tool consistently after successful campaigns.

The library creates a new category of agency intellectual property. It should be treated as confidential business data — not shared externally, not included in client deliverables.

`PromptTemplate` requires its own database table with no `client_id` column. Alembic migrations and access control policies must reflect this difference from client-scoped entities.

## Implementation status

| Component | Status |
|-----------|--------|
| `PromptTemplate` ORM model in `db/models.py` (no `client_id`) | ✅ Implemented |
| Migration `0005_add_prompt_templates.py` (no RLS — agency-wide) | ✅ Implemented |
| `schemas/prompt_template.py` — `PromoteToLibraryInput/Response`, `PromptTemplateSuggestion` | ✅ Implemented |
| `services/prompt_library_service.py` — `promote_to_library`, `get_library_suggestions` | ✅ Implemented |
| `tools/promote_to_library.py` — MCP tool with anonymization checklist | ✅ Implemented |
| Unit tests — `tests/services/test_prompt_library_service.py` | ✅ Implemented |
| `create_creative_sprint` — `library_suggestions` in response | ⏳ Deferred to Milestone 3 |

## Impact on VOS Studio MCP

- `db/models.py` — `PromptTemplate` model (no `client_id`, agency-wide).
- `db/migrations/versions/0005_add_prompt_templates.py` — table, no RLS restriction.
- `src/vos_studio_mcp/schemas/prompt_template.py` — input/response schemas.
- `src/vos_studio_mcp/services/prompt_library_service.py` — promotion + suggestion query.
- `src/vos_studio_mcp/tools/promote_to_library.py` — MCP tool registered in `tools/__init__.py`.
- `confirmed=False` preview mode shows anonymization checklist; `confirmed=True` saves to DB.
- Placeholder validation: `prompt_template` must contain `{{` before saving.
