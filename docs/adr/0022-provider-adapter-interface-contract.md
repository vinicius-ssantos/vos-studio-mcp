# ADR-0022 — Provider adapter interface contract

Status: Amended  
Date: 2026-05-21  
Amended: 2026-05-22

## Context

ADR-0009 decided that provider integrations (Higgsfield, Freepik, Magnific, and manual dashboard) will be implemented as adapters behind a common internal interface.

The original decision defined this contract as a TypeScript interface. With the switch to Python (ADR-0001 amended), the contract is redefined using Python's `typing.Protocol` — which provides structural subtyping (duck typing with static checking) without requiring inheritance.

The interface was subsequently extended in two ways:
1. `verify_webhook_signature` was added to support ADR-0028 (provider webhook support).
2. `GenerationParams` was extended with provider-specific content fields used by API-backed adapters (first implemented for `HiggsFieldAdapter`).

## Decision

All provider adapters must implement the following Python `Protocol`:

```python
from typing import Protocol, Literal, runtime_checkable
from dataclasses import dataclass, field


@dataclass
class BudgetLimit:
    max_spend_usd: float
    max_images: int | None = None
    max_videos: int | None = None


@dataclass
class GenerationParams:
    sprint_id: str
    prompt_version: str       # version identifier per ADR-0013
    preset_version: str       # version identifier per ADR-0013
    mode: Literal["dashboard_manual", "api_credits"]
    budget_limit: BudgetLimit | None = None   # required if mode is api_credits
    approval_token: str | None = None          # required if mode is api_credits
    # Provider-specific content resolved by the caller before invoking the adapter
    prompt: str = ""
    image_url: str | None = None              # for image-to-video providers
    duration_seconds: int = 5
    resolution: str = "720p"
    aspect_ratio: str = "16:9"


@dataclass
class CostEstimate:
    estimated_usd: float
    uncertain: bool = False   # True when local pricing data is unavailable


@dataclass
class AssetReference:
    asset_id: str
    storage_url: str
    preview_url: str


@dataclass
class ActualCost:
    spend_usd: float
    units: int
    unit_type: str   # "image", "video", "upscale", etc.


@dataclass
class GenerationResult:
    job_id: str
    status: Literal["queued", "completed", "failed"]
    asset_ref: AssetReference | None = None   # present if status is completed
    cost: ActualCost | None = None


@dataclass
class ManualPack:
    prompt: str
    provider: str
    model: str
    settings: dict[str, object] = field(default_factory=dict)
    checklist: list[str] = field(default_factory=list)
    naming_convention: str = ""
    qa_criteria: list[str] = field(default_factory=list)
    negative_prompt: str | None = None


@dataclass
class JobStatus:
    job_id: str
    status: Literal["queued", "running", "completed", "failed", "timed_out"]
    progress: float | None = None   # 0.0 to 1.0 if provider supports it
    error: str | None = None


@runtime_checkable
class ProviderAdapter(Protocol):
    provider_id: str

    async def estimate_cost(self, params: GenerationParams) -> CostEstimate: ...

    async def generate_image(self, params: GenerationParams) -> GenerationResult: ...

    async def generate_video(self, params: GenerationParams) -> GenerationResult: ...

    async def check_job_status(self, job_id: str) -> JobStatus: ...

    async def prepare_manual_pack(self, params: GenerationParams) -> ManualPack: ...

    def verify_webhook_signature(
        self, payload: bytes, headers: dict[str, str]
    ) -> bool: ...
```

**Method contracts:**

- `estimate_cost` must return a cost estimate before any paid action is taken. It must never call the provider API — it calculates from local pricing data. If pricing is unknown, it returns a conservative upper-bound with `uncertain=True`.

- `generate_image` and `generate_video` are only valid for adapters in `api_credits` mode (ADR-0003). Manual dashboard adapters must raise `NotImplementedError`. Both methods must require a non-empty `approval_token` in `params` per ADR-0005.

- `check_job_status` returns the current state of an async generation job. For synchronous providers, it may return an immediately resolved result.

- `prepare_manual_pack` is used in `dashboard_manual` mode (ADR-0003). API adapters may implement it to return a preview of what would be sent, but it must not trigger generation.

- `verify_webhook_signature` validates the HMAC or other signature scheme used by the provider. Manual dashboard adapters return `True` by default. Adapters must return `False` (never raise) when the secret is unconfigured or the signature is invalid. See ADR-0028 for the full webhook architecture.

**`GenerationParams` content fields:**

The fields `prompt`, `image_url`, `duration_seconds`, `resolution`, and `aspect_ratio` carry the actual generation content resolved by the service layer before invoking the adapter. They are distinct from `prompt_version` and `preset_version`, which are version identifiers used for tracking per ADR-0013. An adapter that requires a prompt must read from `params.prompt`, falling back to `params.prompt_version` only when `params.prompt` is empty.

## Alternatives considered

- **Abstract Base Class (ABC)**: requires explicit inheritance. More familiar to developers from Java/C#, but forces inheritance where composition is sufficient. Rejected in favor of `Protocol` for structural typing flexibility.
- **TypeScript interface**: original decision. Not applicable after ADR-0001 amendment.
- **No shared contract, duck typing only**: each tool handler checks the provider and calls different methods. Rejected for maintainability reasons.
- **Separate `VideoGenerationParams` subclass**: considered when adding video-specific fields. Rejected — a single flat `GenerationParams` with optional fields is simpler and avoids union types in method signatures.

## Consequences

All adapters (manual, Higgsfield, Freepik, Magnific, future providers) must satisfy the `ProviderAdapter` Protocol. Static type checkers (mypy, pyright) will flag any adapter missing a required method.

Using `Protocol` means adapters do not need to import `ProviderAdapter` — they just need to match the interface. This allows external or community-contributed adapters to satisfy the contract without depending on the internal module.

The async-native design (`async def`) is consistent with FastAPI's async handlers and Celery's async task support.

## Implementation

- `src/vos_studio_mcp/services/providers/base.py` — canonical Protocol and all shared dataclasses
- `src/vos_studio_mcp/services/providers/manual_dashboard.py` — manual dashboard adapter
- `src/vos_studio_mcp/services/providers/higgsfield.py` — Higgsfield video generation adapter
- `src/vos_studio_mcp/services/providers/__init__.py` — adapter registry (`provider_id` → instance)

## Impact on VOS Studio MCP

- Each provider file in `src/vos_studio_mcp/services/providers/` implements the Protocol without inheriting from it.
- Tool handlers receive a `ProviderAdapter` instance from the registry in `providers/__init__.py`.
- The adapter registry is the only place where concrete adapters are instantiated.
- `mypy` strict mode enforces Protocol compliance statically across the codebase.
