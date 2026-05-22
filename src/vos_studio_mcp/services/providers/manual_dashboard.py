import structlog

from src.vos_studio_mcp.services.providers.base import (
    CostEstimate,
    GenerationParams,
    GenerationResult,
    JobStatus,
    ManualPack,
)

log = structlog.get_logger(__name__)


class ManualDashboardAdapter:
    provider_id = "manual_dashboard"

    async def estimate_cost(self, params: GenerationParams) -> CostEstimate:
        # Manual execution has no API cost — only human operator time.
        return CostEstimate(estimated_usd=0.0, uncertain=False)

    async def generate_image(self, params: GenerationParams) -> GenerationResult:
        raise NotImplementedError(
            "manual_dashboard adapter does not support api_credits generation. "
            "Use prepare_manual_pack and register the asset manually."
        )

    async def generate_video(self, params: GenerationParams) -> GenerationResult:
        raise NotImplementedError(
            "manual_dashboard adapter does not support api_credits generation. "
            "Use prepare_manual_pack and register the asset manually."
        )

    async def check_job_status(self, job_id: str) -> JobStatus:
        # Manual jobs are always in operator hands — status is not machine-trackable.
        return JobStatus(job_id=job_id, status="queued")

    async def prepare_manual_pack(self, params: GenerationParams) -> ManualPack:
        log.info(
            "preparing_manual_pack",
            sprint_id=params.sprint_id,
            prompt_version=params.prompt_version,
            preset_version=params.preset_version,
        )
        return ManualPack(
            prompt="",  # populated by the prompt service in Milestone 2
            provider="manual_dashboard",
            model="",
            checklist=[
                "Confirm prompt matches brand kit restrictions",
                "Verify aspect ratio matches campaign format",
                "Record asset name using the naming convention",
                "Register asset via register_manual_asset after generation",
            ],
            naming_convention=f"spr-{params.sprint_id}-{params.prompt_version}",
            qa_criteria=[
                "No forbidden elements from brand kit restrictions",
                "Asset matches expected output format",
            ],
        )

    def verify_webhook_signature(
        self, payload: bytes, headers: dict[str, str]
    ) -> bool:
        # Manual dashboard never sends webhooks.
        return True
