"""Higgsfield video generation provider adapter (ADR-0009)."""

import hashlib
import hmac
import logging
from typing import Any, Literal

import httpx

from vos_studio_mcp.config.env import get_settings
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.services.circuit_breaker import get_breaker
from vos_studio_mcp.services.providers.base import (
    CostEstimate,
    GenerationParams,
    GenerationResult,
    JobStatus,
    ManualPack,
)

log = logging.getLogger(__name__)

_BASE_URL = "https://api.higgsfield.ai"

_COST_TABLE: dict[tuple[str, int], float] = {
    ("480p", 5): 0.04,
    ("480p", 10): 0.08,
    ("720p", 5): 0.06,
    ("720p", 10): 0.12,
    ("1080p", 5): 0.10,
    ("1080p", 10): 0.20,
}
_DEFAULT_COST_USD = 0.10

_STATUS_MAP: dict[str, Literal["queued", "running", "completed", "failed"]] = {
    "QUEUED": "queued",
    "PROCESSING": "running",
    "COMPLETED": "completed",
    "FAILED": "failed",
    "ERROR": "failed",
}


class HiggsFieldAdapter:
    provider_id = "higgsfield"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {get_settings().higgsfield_api_key}",
            "Content-Type": "application/json",
        }

    async def estimate_cost(self, params: GenerationParams) -> CostEstimate:
        key = (params.resolution, params.duration_seconds)
        cost = _COST_TABLE.get(key, _DEFAULT_COST_USD)
        return CostEstimate(estimated_usd=cost, uncertain=True)

    async def generate_image(self, params: GenerationParams) -> GenerationResult:
        raise NotImplementedError(
            "higgsfield adapter does not support image generation. Use generate_video."
        )

    async def generate_video(self, params: GenerationParams) -> GenerationResult:
        settings = get_settings()
        if not settings.higgsfield_api_key:
            raise VosError(ErrorCode.PROVIDER_ERROR, "HIGGSFIELD_API_KEY is not configured")

        if params.mode == "api_credits" and not params.approval_token:
            raise VosError(ErrorCode.INVALID_INPUT, "approval_token is required for api_credits mode")

        prompt = params.prompt or params.prompt_version

        if params.image_url:
            endpoint = f"{_BASE_URL}/v1/image2video/dop"
            payload: dict[str, Any] = {
                "prompt": prompt,
                "image_url": params.image_url,
                "duration": params.duration_seconds,
                "resolution": params.resolution,
                "aspect_ratio": params.aspect_ratio,
            }
        else:
            endpoint = f"{_BASE_URL}/v1/video/generate"
            payload = {
                "prompt": prompt,
                "duration": params.duration_seconds,
                "resolution": params.resolution,
                "aspect_ratio": params.aspect_ratio,
            }

        log.info(
            "higgsfield.generate_video",
            extra={"sprint_id": params.sprint_id, "prompt_version": params.prompt_version},
        )

        breaker = get_breaker("higgsfield")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await breaker.execute(
                client.post(endpoint, headers=self._headers(), json=payload)
            )

        if response.status_code == 402:
            raise VosError(ErrorCode.BUDGET_EXCEEDED, "Higgsfield API: insufficient credits")
        if response.status_code == 401:
            raise VosError(ErrorCode.PROVIDER_ERROR, "Higgsfield API: authentication failed")
        if not response.is_success:
            log.warning(
                "higgsfield.generate_video.error",
                extra={"status_code": response.status_code},
            )
            raise VosError(
                ErrorCode.PROVIDER_ERROR,
                f"Higgsfield API returned {response.status_code}",
            )

        data: dict[str, Any] = response.json()
        job_id: str = str(data.get("generation_id") or data.get("request_id") or "")

        return GenerationResult(job_id=job_id, status="queued")

    async def check_job_status(self, job_id: str) -> JobStatus:
        if not get_settings().higgsfield_api_key:
            raise VosError(ErrorCode.PROVIDER_ERROR, "HIGGSFIELD_API_KEY is not configured")

        breaker = get_breaker("higgsfield")
        status_url = f"{_BASE_URL}/v1/video/status/{job_id}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await breaker.execute(
                client.get(status_url, headers=self._headers())
            )

        if not response.is_success:
            raise VosError(
                ErrorCode.PROVIDER_ERROR,
                f"Higgsfield status check returned {response.status_code}",
            )

        data: dict[str, Any] = response.json()
        raw_status = str(data.get("status", "QUEUED")).upper()
        mapped = _STATUS_MAP.get(raw_status, "queued")

        error: str | None = None
        if mapped == "failed":
            error = str(data.get("error") or data.get("message") or "generation failed")

        media_url: str | None = None
        if mapped == "completed":
            output: dict[str, Any] = data.get("output") or {}
            media_url = output.get("media_url") or None

        return JobStatus(job_id=job_id, status=mapped, error=error, media_url=media_url)

    async def prepare_manual_pack(self, params: GenerationParams) -> ManualPack:
        prompt = params.prompt or params.prompt_version
        return ManualPack(
            prompt=prompt,
            provider="higgsfield",
            model="dop",
            settings={
                "resolution": params.resolution,
                "duration_seconds": params.duration_seconds,
                "aspect_ratio": params.aspect_ratio,
            },
            checklist=[
                "Log in to higgsfield.ai and navigate to Image-to-Video",
                "Upload the reference image from the brand kit",
                f"Set resolution to {params.resolution}, duration to {params.duration_seconds}s, "
                f"aspect ratio {params.aspect_ratio}",
                "Paste the prompt below into the prompt field",
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

    def verify_webhook_signature(
        self, payload: bytes, headers: dict[str, str]
    ) -> bool:
        secret = get_settings().webhook_secret_higgsfield
        if not secret:
            log.warning("webhook_secret_higgsfield not configured — rejecting webhook")
            return False

        sig_header = (
            headers.get("X-Higgsfield-Signature")
            or headers.get("x-higgsfield-signature", "")
        )
        if not sig_header:
            return False

        sig_value = sig_header.removeprefix("sha256=")
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig_value)
