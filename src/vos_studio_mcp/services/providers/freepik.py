"""Freepik image generation provider adapter (ADR-0009)."""

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

_BASE_URL = "https://api.freepik.com/v1"

_COST_PER_IMAGE_USD = 0.01

_STATUS_MAP: dict[str, Literal["queued", "running", "completed", "failed"]] = {
    "IN_PROGRESS": "running",
    "PENDING": "queued",
    "COMPLETED": "completed",
    "FAILED": "failed",
    "CANCELLED": "failed",
}


class FreepikAdapter:
    provider_id = "freepik"

    def _headers(self) -> dict[str, str]:
        return {
            "x-freepik-api-key": get_settings().freepik_api_key,
            "Content-Type": "application/json",
        }

    async def estimate_cost(self, params: GenerationParams) -> CostEstimate:
        return CostEstimate(estimated_usd=_COST_PER_IMAGE_USD, uncertain=False)

    async def generate_image(self, params: GenerationParams) -> GenerationResult:
        settings = get_settings()
        if not settings.freepik_api_key:
            raise VosError(ErrorCode.PROVIDER_ERROR, "FREEPIK_API_KEY is not configured")

        if params.mode == "api_credits" and not params.approval_token:
            raise VosError(
                ErrorCode.INVALID_INPUT, "approval_token is required for api_credits mode"
            )

        prompt = params.prompt or params.prompt_version
        payload: dict[str, Any] = {
            "prompt": prompt,
            "num_images": 1,
            "image": {
                "size": _map_resolution(params.resolution),
            },
        }

        log.info(
            "freepik.generate_image",
            extra={"sprint_id": params.sprint_id, "prompt_version": params.prompt_version},
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{_BASE_URL}/ai/text-to-image",
                headers=self._headers(),
                json=payload,
            )

        if response.status_code == 402:
            raise VosError(ErrorCode.BUDGET_EXCEEDED, "Freepik API: insufficient credits")
        if response.status_code == 401:
            raise VosError(ErrorCode.PROVIDER_AUTH_ERROR, "Freepik API: authentication failed")
        if not response.is_success:
            log.warning(
                "freepik.generate_image.error",
                extra={"status_code": response.status_code},
            )
            raise VosError(
                ErrorCode.PROVIDER_ERROR,
                f"Freepik API returned {response.status_code}",
            )

        data: dict[str, Any] = response.json()
        task_id: str = str(data.get("data", {}).get("task_id") or data.get("task_id") or "")
        return GenerationResult(job_id=task_id, status="queued")

    async def generate_video(self, params: GenerationParams) -> GenerationResult:
        raise NotImplementedError(
            "freepik adapter does not support video generation. "
            "Use higgsfield for video generation."
        )

    async def check_job_status(self, job_id: str) -> JobStatus:
        if not get_settings().freepik_api_key:
            raise VosError(ErrorCode.PROVIDER_ERROR, "FREEPIK_API_KEY is not configured")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{_BASE_URL}/ai/text-to-image/{job_id}",
                headers=self._headers(),
            )

        if not response.is_success:
            raise VosError(
                ErrorCode.PROVIDER_ERROR,
                f"Freepik status check returned {response.status_code}",
            )

        data: dict[str, Any] = response.json()
        task_data: dict[str, Any] = data.get("data", data)
        raw_status = str(task_data.get("status", "PENDING")).upper()
        mapped = _STATUS_MAP.get(raw_status, "queued")

        error: str | None = None
        if mapped == "failed":
            error = str(task_data.get("error") or "generation failed")

        media_url: str | None = None
        if mapped == "completed":
            generated: list[dict[str, Any]] = task_data.get("generated", [])
            if generated:
                media_url = generated[0].get("url")

        return JobStatus(job_id=job_id, status=mapped, error=error, media_url=media_url)

    async def prepare_manual_pack(self, params: GenerationParams) -> ManualPack:
        prompt = params.prompt or params.prompt_version
        return ManualPack(
            prompt=prompt,
            provider="freepik",
            model="mystic",
            settings={"resolution": params.resolution, "aspect_ratio": params.aspect_ratio},
            checklist=[
                "Log in to freepik.com and navigate to AI Image Generator",
                "Select the Mystic model for best quality results",
                f"Set image size to match {params.resolution} / {params.aspect_ratio}",
                "Paste the prompt below and add any style modifiers from the brand kit",
                "Confirm no brand kit restrictions are violated before generating",
                "Download the completed image",
                "Register the asset via register_manual_asset",
            ],
            naming_convention=f"spr-{params.sprint_id}-{params.prompt_version}",
            qa_criteria=[
                "No forbidden elements from brand kit restrictions",
                "Image resolution and aspect ratio match campaign format",
                "Brand colors consistent with brand kit visual spec",
                "No AI artifacts (hands, text, distorted faces)",
            ],
        )

    def verify_webhook_signature(self, payload: bytes, headers: dict[str, str]) -> bool:
        secret = get_settings().webhook_secret_freepik
        if not secret:
            log.warning("webhook_secret_freepik not configured — rejecting webhook")
            return False

        sig_header = (
            headers.get("X-Freepik-Signature") or headers.get("x-freepik-signature", "")
        )
        if not sig_header:
            return False

        sig_value = sig_header.removeprefix("sha256=")
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig_value)


def _map_resolution(resolution: str) -> str:
    _map = {"480p": "square_1_1", "720p": "widescreen_16_9", "1080p": "widescreen_16_9"}
    return _map.get(resolution, "square_1_1")
