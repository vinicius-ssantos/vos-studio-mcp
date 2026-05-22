"""Generation service — request API-based video generation (ADR-0005, ADR-0009)."""

import logging
import uuid

from sqlalchemy import func, select

from db.models import Asset, Sprint
from vos_studio_mcp.auth.guards import assert_owns_client
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.api_video import ApiVideoInput, ApiVideoResponse, VideoJobStatusResponse
from vos_studio_mcp.services.database import get_asset_with_client, get_session, set_tenant_context
from vos_studio_mcp.services.providers import get_adapter
from vos_studio_mcp.services.providers.base import BudgetLimit, GenerationParams
from vos_studio_mcp.tasks.poll_video import poll_video_job

log = logging.getLogger(__name__)


async def request_api_video(data: ApiVideoInput) -> ApiVideoResponse:
    assert_owns_client(data.client_id)

    adapter = get_adapter("higgsfield")

    params = GenerationParams(
        sprint_id=data.sprint_id,
        prompt_version=data.prompt_version,
        preset_version=data.preset_version,
        mode="api_credits",
        approval_token=data.approval_token,
        prompt=data.prompt,
        image_url=data.image_url,
        duration_seconds=data.duration_seconds,
        resolution=data.resolution,
        aspect_ratio=data.aspect_ratio,
    )

    estimate = await adapter.estimate_cost(params)

    async with get_session() as session:
        await set_tenant_context(session, data.client_id)

        sprint = await session.get(Sprint, uuid.UUID(data.sprint_id))
        if sprint is None:
            raise VosError(ErrorCode.NOT_FOUND, f"Sprint {data.sprint_id} not found")
        if str(sprint.client_id) != data.client_id:
            raise VosError(ErrorCode.INVALID_INPUT, "sprint does not belong to this client")
        if sprint.sprint_status != "open":
            raise VosError(ErrorCode.SPRINT_CLOSED, f"Sprint {data.sprint_id} is not open")

        if sprint.spent_usd + estimate.estimated_usd > sprint.max_spend_usd:
            raise VosError(
                ErrorCode.BUDGET_EXCEEDED,
                f"Generation would exceed sprint budget "
                f"(remaining ${sprint.max_spend_usd - sprint.spent_usd:.2f}, "
                f"estimated ${estimate.estimated_usd:.2f})",
            )

        if sprint.max_videos is not None:
            video_count_result = await session.execute(
                select(func.count()).where(
                    Asset.sprint_id == sprint.id,
                    Asset.provider == "higgsfield",
                )
            )
            video_count = video_count_result.scalar_one()
            if video_count >= sprint.max_videos:
                raise VosError(
                    ErrorCode.BUDGET_EXCEEDED,
                    f"Sprint video limit reached ({sprint.max_videos} videos allowed)",
                )

        params.budget_limit = BudgetLimit(
            max_spend_usd=sprint.max_spend_usd,
            max_videos=sprint.max_videos,
        )

        log.info(
            "generation.requested",
            extra={"sprint_id": data.sprint_id, "provider": "higgsfield"},
        )
        result = await adapter.generate_video(params)
        log.info(
            "generation.provider_submitted",
            extra={"sprint_id": data.sprint_id, "job_id": result.job_id, "provider": "higgsfield"},
        )

        asset = Asset(
            sprint_id=sprint.id,
            provider="higgsfield",
            prompt_version=data.prompt_version,
            preset_version=data.preset_version,
            storage_url=None,
            provider_job_id=result.job_id,
            generation_status="pending",
        )
        session.add(asset)

        sprint.spent_usd += estimate.estimated_usd
        await session.commit()
        await session.refresh(asset)

    poll_video_job.delay(str(asset.id))

    log.info(
        "generation.queued",
        extra={
            "sprint_id": data.sprint_id,
            "asset_id": str(asset.id),
            "job_id": result.job_id,
            "provider": "higgsfield",
            "estimated_usd": estimate.estimated_usd,
        },
    )

    return ApiVideoResponse(
        status="queued",
        job_id=result.job_id,
        asset_id=str(asset.id),
        sprint_id=data.sprint_id,
        estimated_cost_usd=estimate.estimated_usd,
        summary=(
            f"Video generation queued for sprint '{data.sprint_id}'. "
            f"Job ID: {result.job_id}. Estimated cost: ${estimate.estimated_usd:.2f}."
        ),
        next_action="get_video_job_status",
    )


_NEXT_ACTION: dict[str, str] = {
    "pending": "get_video_job_status",
    "processing": "get_video_job_status",
    "completed": "prepare_dashboard_pack",
    "failed": "request_api_video",
    "manual": "list_sprint_assets",
}

_SUMMARY: dict[str, str] = {
    "pending": "Video generation is queued. Poll again shortly.",
    "processing": "Video generation is in progress. Poll again shortly.",
    "completed": "Video is ready in storage.",
    "failed": "Video generation failed. You may retry with request_api_video.",
    "manual": "Asset was registered manually — no generation job.",
}


async def get_video_job_status(asset_id: str) -> VideoJobStatusResponse:
    """Return generation status for an asset without calling the provider API."""
    async with get_session() as session:
        asset, client_id = await get_asset_with_client(session, asset_id)

    if asset is None or client_id is None:
        raise VosError(ErrorCode.NOT_FOUND, f"Asset {asset_id} not found")

    assert_owns_client(client_id)

    gen_status = asset.generation_status
    return VideoJobStatusResponse(
        status="ok",
        asset_id=asset_id,
        generation_status=gen_status,
        storage_url=asset.storage_url,
        provider_job_id=asset.provider_job_id,
        summary=_SUMMARY.get(gen_status, f"Unknown status: {gen_status}"),
        next_action=_NEXT_ACTION.get(gen_status, "get_video_job_status"),
    )
