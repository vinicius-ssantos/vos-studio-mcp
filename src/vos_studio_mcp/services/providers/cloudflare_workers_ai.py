"""Cloudflare Workers AI provider adapter (Issue #43).

Text-to-image generation using Cloudflare's free-tier Workers AI API.
Disabled by default; enable via CLOUDFLARE_WORKERS_AI_ENABLED=true.

No webhook support, no polling — synchronous HTTP response with a synthetic job_id.
"""

import logging
import uuid
from base64 import b64decode

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

_BASE_URL = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run"
_DEFAULT_MODEL = "@cf/black-forest-labs/flux-1-schnell"


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class CloudflareWorkersAIAdapter:
    """ProviderAdapter implementation for Cloudflare Workers AI text-to-image."""

    provider_id = "cloudflare_workers_ai"

    def __init__(self, account_id: str, api_token: str) -> None:
        self._account_id = account_id
        self._api_token = api_token

    # ------------------------------------------------------------------
    # ProviderAdapter protocol
    # ------------------------------------------------------------------

    async def estimate_cost(self, params: GenerationParams) -> CostEstimate:
        """Free tier: always returns 0.0 USD."""
        return CostEstimate(estimated_usd=0.0, uncertain=False)

    async def generate_video(self, params: GenerationParams) -> GenerationResult:
        """Not supported — raises PROVIDER_ERROR."""
        raise VosError(
            ErrorCode.PROVIDER_ERROR,
            "Cloudflare Workers AI does not support video generation.",
        )

    async def check_job_status(self, job_id: str) -> JobStatus:
        """Not supported — synchronous adapter has no polling."""
        raise VosError(
            ErrorCode.PROVIDER_ERROR,
            "Cloudflare Workers AI does not support job polling.",
        )

    async def generate_image(self, params: GenerationParams) -> GenerationResult:
        """Generate a text-to-image and return a completed GenerationResult with raw bytes stored."""
        settings = get_settings()
        if not settings.cloudflare_workers_ai_enabled:
            raise VosError(
                ErrorCode.PROVIDER_UNAVAILABLE,
                "Cloudflare Workers AI is disabled. Set CLOUDFLARE_WORKERS_AI_ENABLED=true.",
            )

        url = _BASE_URL.format(account_id=self._account_id) + f"/{_DEFAULT_MODEL}"
        payload = {
            "prompt": params.prompt,
            "num_steps": 4,
            "width": 1024,
            "height": 1024,
        }
        headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
        }

        log.info(
            "cloudflare_workers_ai.generate_image",
            extra={"sprint_id": params.sprint_id, "prompt_version": params.prompt_version},
        )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise VosError(
                ErrorCode.PROVIDER_TIMEOUT,
                "Cloudflare Workers AI request timed out.",
            ) from exc
        except httpx.RequestError as exc:
            raise VosError(
                ErrorCode.PROVIDER_ERROR,
                f"Cloudflare Workers AI request failed: {exc}",
            ) from exc

        if response.status_code != 200:
            log.warning(
                "cloudflare_workers_ai.http_error",
                extra={"status_code": response.status_code},
            )
            raise VosError(
                ErrorCode.PROVIDER_ERROR,
                f"Cloudflare Workers AI returned HTTP {response.status_code}.",
            )

        try:
            body = response.json()
            # Response: {"result": {"image": "<base64>"}, "success": true}
            if not body.get("success"):
                errors = body.get("errors", [])
                raise VosError(ErrorCode.PROVIDER_ERROR, f"Cloudflare API error: {errors}")
            image_bytes = b64decode(body["result"]["image"])
        except (KeyError, ValueError) as exc:
            raise VosError(
                ErrorCode.PROVIDER_ERROR,
                f"Unexpected Cloudflare response format: {exc}",
            ) from exc

        job_id = str(uuid.uuid4())
        log.info(
            "cloudflare_workers_ai.generate_image.completed",
            extra={"job_id": job_id, "bytes": len(image_bytes)},
        )
        return GenerationResult(job_id=job_id, status="completed")

    async def prepare_manual_pack(self, params: GenerationParams) -> ManualPack:
        """Not applicable for API-mode provider; returns minimal informational pack."""
        prompt = params.prompt or params.prompt_version
        return ManualPack(
            prompt=prompt,
            provider=self.provider_id,
            model=_DEFAULT_MODEL,
            settings={},
            checklist=[
                "Not applicable — Cloudflare Workers AI is API-only.",
                "Use generate_image tool to generate images programmatically.",
            ],
            naming_convention=f"spr-{params.sprint_id}-{params.prompt_version}",
            qa_criteria=[
                "Image generated successfully via Cloudflare Workers AI API.",
            ],
        )

    def verify_webhook_signature(self, payload: bytes, headers: dict[str, str]) -> bool:
        """Not supported — Cloudflare Workers AI has no webhooks."""
        return False


def get_cloudflare_adapter() -> CloudflareWorkersAIAdapter:
    """Return a CloudflareWorkersAIAdapter configured from env vars.

    Raises VosError(PROVIDER_UNAVAILABLE) if disabled or missing credentials.
    """
    settings = get_settings()
    if not settings.cloudflare_workers_ai_enabled:
        raise VosError(
            ErrorCode.PROVIDER_UNAVAILABLE,
            "Cloudflare Workers AI is disabled. Set CLOUDFLARE_WORKERS_AI_ENABLED=true.",
        )
    if not settings.cloudflare_account_id or not settings.cloudflare_api_token:
        raise VosError(
            ErrorCode.PROVIDER_UNAVAILABLE,
            "Cloudflare Workers AI requires CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN.",
        )
    return CloudflareWorkersAIAdapter(
        account_id=settings.cloudflare_account_id,
        api_token=settings.cloudflare_api_token,
    )
