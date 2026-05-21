# ADR-0022 — Provider adapter interface contract

Status: Amended  
Date: 2026-05-21  
Amended: 2026-05-21

## Context

ADR-0009 decided that provider integrations (Higgsfield, Freepik, Magnific, and manual dashboard) will be implemented as adapters behind a common internal interface.

The original decision defined this contract as a TypeScript interface. With the switch to Python (ADR-0001 amended), the contract is redefined using Python's `typing.Protocol` — which provides structural subtyping (duck typing with static checking) without requiring inheritance.

## Decision

All provider adapters must implement the following Python `Protocol`:

```python
from typing import Protocol, Literal
from dataclasses import dataclass

@dataclass
class GenerationParams:
    sprint_id: str
    prompt_version: str       # required per ADR-0013
    preset_version: str       # required per ADR-0013
    mode: Literal["dashboard_manual", "api_credits"]
    budget_limit: "BudgetLimit | None" = None   # required if mode is api_credits
    approval_token: str | None = None            # required if mode is api_credits

@dataclass
class CostEstimate:
    estimated_usd: float
    uncertain: bool = False   # True when pricing data is unavailable

@dataclass
class GenerationResult:
    job_id: str
    status: Literal["queued", "completed", "failed"]
    asset_ref: "AssetReference | None" = None   # present if status is completed
    cost: "ActualCost | None" = None

@dataclass
class ManualPack:
    prompt: str
    provider: str
    model: str
    settings: dict
    checklist: list[str]
    naming_convention: str
    qa_criteria: list[str]
    negative_prompt: str | None = None

@dataclass
class JobStatus:
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    progress: float | None = None   # 0.0 to 1.0 if provider supports it
    error: str | None = None


class ProviderAdapter(Protocol):
    provider_id: str

    async def estimate_cost(self, params: GenerationParams) -> CostEstimate: ...

    async def generate_image(self, params: GenerationParams) -> GenerationResult: ...

    async def generate_video(self, params: GenerationParams) -> GenerationResult: ...

    async def check_job_status(self, job_id: str) -> JobStatus: ...

    async def prepare_manual_pack(self, params: GenerationParams) -> ManualPack: ...
```

**Method contracts:**

- `estimate_cost` must return a cost estimate before any paid action is taken. It must never call the provider API — it calculates from local pricing data. If pricing is unknown, it returns a conservative upper-bound with `uncertain=True`.

- `generate_image` and `generate_video` are only valid for adapters in `api_credits` mode (ADR-0003). Manual dashboard adapters must raise `NotImplementedError` for these methods.

- `check_job_status` returns the current state of an async generation job. For synchronous providers, it may return an immediately resolved result.

- `prepare_manual_pack` is only valid for adapters in `dashboard_manual` mode (ADR-0003). API adapters may implement it to return a preview of what would be sent, but it must not trigger generation.

## Alternatives considered

- **Abstract Base Class (ABC)**: requires explicit inheritance (`class HiggsifieldAdapter(ProviderAdapter)`). More familiar to developers coming from Java/C#, but forces inheritance where composition is sufficient. Rejected in favor of `Protocol` for its structural typing flexibility.
- **TypeScript interface**: original decision. Not applicable after ADR-0001 amendment. Rejected.
- **No shared contract, duck typing only**: each tool handler checks the provider and calls different methods. Rejected for the same reasons as the original ADR.

## Consequences

All adapters (manual, Higgsfield, Freepik, Magnific, future providers) must satisfy the `ProviderAdapter` Protocol. Static type checkers (mypy, pyright) will flag any adapter missing a required method.

Using `Protocol` means adapters do not need to import `ProviderAdapter` — they just need to match the interface. This allows external or community-contributed adapters to satisfy the contract without depending on the internal module.

The async-native design (`async def`) is consistent with FastAPI's async handlers and Celery's async task support.

## Impact on VOS Studio MCP

- Create `src/vos_studio_mcp/services/providers/base.py` with the `ProviderAdapter` Protocol and all shared dataclasses.
- Create `src/vos_studio_mcp/services/providers/manual_dashboard.py` as the first implementation, targeting Milestone 2.
- Each provider file in `src/vos_studio_mcp/services/providers/` implements the Protocol without inheriting from it.
- Tool handlers receive a `ProviderAdapter` instance via dependency injection (FastAPI's `Depends()`), not imported directly.
- The adapter registry in `src/vos_studio_mcp/services/providers/__init__.py` maps `provider_id` strings to adapter instances and is the only place where concrete adapters are instantiated.
- Add `mypy` or `pyright` to the development toolchain to enforce Protocol compliance statically.
