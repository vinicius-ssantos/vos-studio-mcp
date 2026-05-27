"""Higgsfield MCP provider adapter — Phase 3 (ADR-0044, Issue #73)."""

import logging
from typing import Any, Literal

from vos_studio_mcp.config.env import get_settings
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.services.mcp_clients.higgsfield import call_tool
from vos_studio_mcp.services.providers.base import (
    CostEstimate,
    GenerationParams,
    GenerationResult,
    JobStatus,
    ManualPack,
)

log = logging.getLogger(__name__)

# Cost table mirrors the REST adapter (conservative, always uncertain)
_COST_TABLE: dict[tuple[str, int], float] = {
    ("480p", 5): 0.04,
    ("480p", 10): 0.08,
    ("720p", 5): 0.06,
    ("720p", 10): 0.12,
    ("1080p", 5): 0.10,
    ("1080p", 10): 0.20,
}
_DEFAULT_COST_USD = 0.10

# Tool names as exposed by the Higgsfield MCP server.
# Update these constants if the real server uses different names (discovered via
# list_higgsfield_mcp_capabilities).
_TOOL_GENERATE_VIDEO = "generate_video"
_TOOL_GENERATE_IMAGE_TO_VIDEO = "generate_image_to_video"
_TOOL_JOB_STATUS = "job_display"

_STATUS_MAP: dict[str, Literal["queued", "running", "completed", "failed"]] = {
    "QUEUED": "queued",
    "PROCESSING": "running",
    "COMPLETED": "completed",
    "FAILED": "failed",
    "ERROR": "failed",
}


class HiggsFieldMcpAdapter:
    """Provider adapter that calls the official Higgsfield MCP server (ADR-0044)."""

    provider_id = "higgsfield_mcp"

    async def estimate_cost(self, params: GenerationParams) -> CostEstimate:
        key = (params.resolution, params.duration_seconds)
        cost = _COST_TABLE.get(key, _DEFAULT_COST_USD)
        return CostEstimate(estimated_usd=cost, uncertain=True)

    async def generate_image(self, params: GenerationParams) -> GenerationResult:
        raise NotImplementedError(
            "higgsfield_mcp adapter does not support image generation. Use generate_video."
        )

    async def generate_video(self, params: GenerationParams) -> GenerationResult:
        settings = get_settings()
        if not settings.higgsfield_mcp_enabled:
            raise VosError(ErrorCode.PROVIDER_ERROR, "HIGGSFIELD_MCP_ENABLED is not set to true")
        if not settings.higgsfield_mcp_access_token:
            raise VosError(ErrorCode.PROVIDER_ERROR, "HIGGSFIELD_MCP_ACCESS_TOKEN is not configured")

        if params.mode == "api_credits" and not params.approval_token:
            raise VosError(
                ErrorCode.INVALID_INPUT, "approval_token is required for api_credits mode"
            )

        prompt = params.prompt or params.prompt_version

        if params.image_url:
            tool_name = _TOOL_GENERATE_IMAGE_TO_VIDEO
            arguments: dict[str, Any] = {
                "prompt": prompt,
                "image_url": params.image_url,
                "duration": params.duration_seconds,
                "resolution": params.resolution,
                "aspect_ratio": params.aspect_ratio,
            }
        else:
            tool_name = _TOOL_GENERATE_VIDEO
            arguments = {
                "prompt": prompt,
                "duration": params.duration_seconds,
                "resolution": params.resolution,
                "aspect_ratio": params.aspect_ratio,
            }

        log.info(
            "higgsfield_mcp.generate_video",
            extra={"sprint_id": params.sprint_id, "prompt_version": params.prompt_version},
        )

        result = await call_tool(tool_name, arguments)

        job_id = str(
            result.get("generation_id") or result.get("job_id") or result.get("request_id") or ""
        )
        if not job_id:
            raise VosError(
                ErrorCode.PROVIDER_ERROR,
                "Higgsfield MCP generate_video did not return a job ID",
            )

        return GenerationResult(job_id=job_id, status="queued")

    async def check_job_status(self, job_id: str) -> JobStatus:
        settings = get_settings()
        if not settings.higgsfield_mcp_access_token:
            raise VosError(ErrorCode.PROVIDER_ERROR, "HIGGSFIELD_MCP_ACCESS_TOKEN is not configured")

        result = await call_tool(_TOOL_JOB_STATUS, {"generation_id": job_id})

        raw_status = str(result.get("status", "QUEUED")).upper()
        mapped = _STATUS_MAP.get(raw_status, "queued")

        error: str | None = None
        if mapped == "failed":
            error = str(result.get("error") or result.get("message") or "generation failed")

        media_url: str | None = None
        if mapped == "completed":
            output: dict[str, Any] = result.get("output") or {}
            media_url = output.get("media_url") or result.get("media_url") or None

        return JobStatus(job_id=job_id, status=mapped, error=error, media_url=media_url)

    async def prepare_manual_pack(self, params: GenerationParams) -> ManualPack:
        prompt = params.prompt or params.prompt_version
        return ManualPack(
            prompt=prompt,
            provider="higgsfield_mcp",
            model="dop",
            settings={
                "resolution": params.resolution,
                "duration_seconds": params.duration_seconds,
                "aspect_ratio": params.aspect_ratio,
            },
            checklist=[
                "Ensure HIGGSFIELD_MCP_ENABLED=true and HIGGSFIELD_MCP_ACCESS_TOKEN is set",
                "Use list_higgsfield_mcp_capabilities to verify the MCP connection is healthy",
                "Log in to higgsfield.ai and navigate to Image-to-Video",
                "Upload the reference image from the brand kit",
                (
                    f"Set resolution to {params.resolution}, duration to "
                    f"{params.duration_seconds}s, aspect ratio {params.aspect_ratio}"
                ),
                "Paste the prompt into the prompt field",
                "Confirm no brand kit restrictions are violated before generating",
                "Download the completed video",
                "Register the asset via register_manual_asset",
            ],
            naming_convention=f"spr-{params.sprint_id}-{params.prompt_version}",
            qa_criteria=[
                "No forbidden elements from brand kit restrictions",
                "Video resolution and aspect ratio match campaign format",
                "Talent release obtained if human faces appear",
                "Brand logo/colors consistent with brand kit visual spec",
            ],
        )

    def verify_webhook_signature(self, payload: bytes, headers: dict[str, str]) -> bool:
        # Higgsfield MCP server does not deliver webhooks to VOS
        return False
