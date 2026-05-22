"""Magnific image upscaling provider adapter (ADR-0009)."""

import hashlib
import hmac
import logging
from typing import Any, Literal

import httpx

from vos_studio_mcp.config.env import get_settings
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.services.providers.base import (
    CostEstimate,
    GenerationParams,
    GenerationResult,
    JobStatus,
    ManualPack,
)

log = logging.getLogger(__name__)

_BASE_URL = "https://api.magnific.ai/v1"

_COST_PER_UPSCALE_USD = 0.05

_STATUS_MAP: dict[str, Literal["queued", "running", "completed", "failed"]] = {
    "queued": "queued",
    "processing": "running",
    "completed": "completed",
    "failed": "failed",
    "error": "failed",
}


class MagnificAdapter:
    provider_id = "magnific"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {get_settings().magnific_api_key}",
            "Content-Type": "application/json",
        }

    async def estimate_cost(self, params: GenerationParams) -> CostEstimate:
        return CostEstimate(estimated_usd=_COST_PER_UPSCALE_USD, uncertain=False)

    async def generate_image(self, params: GenerationParams) -> GenerationResult:
        """Upscale an image via Magnific. params.image_url is required."""
        settings = get_settings()
        if not settings.magnific_api_key:
            raise VosError(ErrorCode.PROVIDER_ERROR, "MAGNIFIC_API_KEY is not configured")

        if not params.image_url:
            raise VosError(
                ErrorCode.INVALID_INPUT,
                "image_url is required for Magnific upscaling",
            )

        if params.mode == "api_credits" and not params.approval_token:
            raise VosError(
                ErrorCode.INVALID_INPUT, "approval_token is required for api_credits mode"
            )

        scale = _resolution_to_scale(params.resolution)
        payload: dict[str, Any] = {
            "image_url": params.image_url,
            "scale": scale,
            "optimizationType": "QUALITY",
        }

        log.info(
            "magnific.upscale_image",
            extra={"sprint_id": params.sprint_id, "scale": scale},
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{_BASE_URL}/upscaling",
                headers=self._headers(),
                json=payload,
            )

        if response.status_code == 402:
            raise VosError(ErrorCode.BUDGET_EXCEEDED, "Magnific API: insufficient credits")
        if response.status_code == 401:
            raise VosError(ErrorCode.PROVIDER_AUTH_ERROR, "Magnific API: authentication failed")
        if not response.is_success:
            log.warning(
                "magnific.upscale_image.error",
                extra={"status_code": response.status_code},
            )
            raise VosError(
                ErrorCode.PROVIDER_ERROR,
                f"Magnific API returned {response.status_code}",
            )

        data: dict[str, Any] = response.json()
        job_id: str = str(data.get("id") or data.get("job_id") or "")
        return GenerationResult(job_id=job_id, status="queued")

    async def generate_video(self, params: GenerationParams) -> GenerationResult:
        raise NotImplementedError(
            "magnific adapter does not support video generation. "
            "Use higgsfield for video generation."
        )

    async def check_job_status(self, job_id: str) -> JobStatus:
        if not get_settings().magnific_api_key:
            raise VosError(ErrorCode.PROVIDER_ERROR, "MAGNIFIC_API_KEY is not configured")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{_BASE_URL}/upscaling/{job_id}",
                headers=self._headers(),
            )

        if not response.is_success:
            raise VosError(
                ErrorCode.PROVIDER_ERROR,
                f"Magnific status check returned {response.status_code}",
            )

        data: dict[str, Any] = response.json()
        raw_status = str(data.get("status", "queued")).lower()
        mapped = _STATUS_MAP.get(raw_status, "queued")

        error: str | None = None
        if mapped == "failed":
            error = str(data.get("error") or "upscaling failed")

        media_url: str | None = None
        if mapped == "completed":
            media_url = data.get("output_url") or data.get("url")

        return JobStatus(job_id=job_id, status=mapped, error=error, media_url=media_url)

    async def prepare_manual_pack(self, params: GenerationParams) -> ManualPack:
        return ManualPack(
            prompt=params.prompt or "",
            provider="magnific",
            model="magnific-upscaler",
            settings={
                "scale": _resolution_to_scale(params.resolution),
                "optimization_type": "QUALITY",
            },
            checklist=[
                "Log in to magnific.ai",
                "Upload the source image to be upscaled",
                f"Set scale factor to {_resolution_to_scale(params.resolution)}x",
                "Select QUALITY optimization for best results",
                "Wait for upscaling to complete (typically 1–2 minutes)",
                "Download the upscaled image",
                "Register the asset via register_manual_asset",
            ],
            naming_convention=f"spr-{params.sprint_id}-{params.prompt_version}-upscaled",
            qa_criteria=[
                "Upscaled image is sharper than the source with no artifacts",
                "No hallucinated details that differ from the source",
                "Resolution increase matches the requested scale",
                "File size is within delivery format limits",
            ],
        )

    def verify_webhook_signature(self, payload: bytes, headers: dict[str, str]) -> bool:
        secret = get_settings().webhook_secret_magnific
        if not secret:
            log.warning("webhook_secret_magnific not configured — rejecting webhook")
            return False

        sig_header = (
            headers.get("X-Magnific-Signature") or headers.get("x-magnific-signature", "")
        )
        if not sig_header:
            return False

        sig_value = sig_header.removeprefix("sha256=")
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig_value)


def _resolution_to_scale(resolution: str) -> int:
    _map = {"480p": 2, "720p": 2, "1080p": 4, "4k": 4}
    return _map.get(resolution, 2)
