from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable


@dataclass
class BudgetLimit:
    max_spend_usd: float
    max_images: int | None = None
    max_videos: int | None = None


@dataclass
class GenerationParams:
    sprint_id: str
    prompt_version: str      # required per ADR-0013
    preset_version: str      # required per ADR-0013
    mode: Literal["dashboard_manual", "api_credits"]
    budget_limit: BudgetLimit | None = None   # required if mode is api_credits
    approval_token: str | None = None          # required if mode is api_credits


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
    asset_ref: AssetReference | None = None
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
    progress: float | None = None   # 0.0–1.0 if provider supports it
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
