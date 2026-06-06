"""Generation service — request API-based video generation (ADR-0005, ADR-0009)."""

import logging
import uuid
from typing import Any

from sqlalchemy import func, select

from db.models import Asset, Sprint
from vos_studio_mcp.auth.guards import assert_owns_client
from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.api_video import (
    ApiVideoInput,
    ApiVideoResponse,
    JobCounts,
    ListVideoJobsResponse,
    VideoJobStatusResponse,
    VideoJobSummary,
)
from vos_studio_mcp.services.audit_service import AuditAction, AuditResult, emit_audit_event
from vos_studio_mcp.services.budget_guard import check_provider_budget
from vos_studio_mcp.services.database import get_asset_with_client, get_session, set_tenant_context
from vos_studio_mcp.services.providers import get_adapter
from vos_studio_mcp.services.providers.base import BudgetLimit, GenerationParams
from vos_studio_mcp.services.rate_limiter import check_rate_limit
from vos_studio_mcp.tasks.poll_video import poll_video_job

log = logging.getLogger(__name__)


async def request_api_video(data: ApiVideoInput) -> ApiVideoResponse:
    """Submit an API-credit video generation.

    Orchestration only: each step below is an explicit, single-responsibility
    workflow stage (ADR-0039 #2 — validate request, reserve budget, submit
    provider job, register asset + linkage, enqueue follow-up, emit audit).
    """
    assert_owns_client(data.client_id)
    await check_rate_limit("request_api_video", data.client_id)

    adapter = get_adapter(data.provider)
    params = _build_generation_params(data)
    estimate = await adapter.estimate_cost(params)

    # Step 1 — validate the sprint and pre-check budget/limits.
    async with get_session() as session:
        await set_tenant_context(session, data.client_id)
        params.budget_limit = await _validate_sprint_budget(
            session, data, estimate.estimated_usd
        )

    # Step 2 — reserve the global provider daily quota (outside the session to
    # avoid holding the DB connection during the extra async query).
    usage_event_id = await check_provider_budget(
        data.provider, data.client_id, data.sprint_id, estimate.estimated_usd
    )

    # Step 3 — submit the provider job and register the asset under a lock.
    asset_id, job_id = await _submit_and_register(
        adapter, data, params, estimate.estimated_usd, usage_event_id
    )

    # Step 4 — enqueue polling and emit the audit trail.
    poll_video_job.delay(asset_id)
    await _emit_request_audit(data, asset_id, estimate.estimated_usd)

    log.info(
        "generation.queued",
        extra={
            "sprint_id": data.sprint_id,
            "asset_id": asset_id,
            "job_id": job_id,
            "provider": data.provider,
            "estimated_usd": estimate.estimated_usd,
        },
    )

    return ApiVideoResponse(
        status="queued",
        job_id=job_id,
        asset_id=asset_id,
        sprint_id=data.sprint_id,
        estimated_cost_usd=estimate.estimated_usd,
        summary=(
            f"Video generation queued for sprint '{data.sprint_id}'. "
            f"Job ID: {job_id}. Estimated cost: ${estimate.estimated_usd:.2f}."
        ),
        next_action="get_video_job_status",
    )


def _build_generation_params(data: ApiVideoInput) -> GenerationParams:
    """Translate the tool input into a provider-agnostic GenerationParams."""
    return GenerationParams(
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


async def _validate_sprint_budget(
    session: Any, data: ApiVideoInput, estimated_usd: float
) -> BudgetLimit:
    """Validate the sprint is usable and the request fits budget/video limits.

    Returns the BudgetLimit to attach to the provider request. Raises VosError
    on any violation (not found, wrong owner, closed, budget, video count).
    """
    sprint = await session.get(Sprint, uuid.UUID(data.sprint_id))
    if sprint is None:
        raise VosError(ErrorCode.NOT_FOUND, f"Sprint {data.sprint_id} not found")
    if str(sprint.client_id) != data.client_id:
        raise VosError(ErrorCode.INVALID_INPUT, "sprint does not belong to this client")
    if sprint.sprint_status != "open":
        raise VosError(ErrorCode.SPRINT_CLOSED, f"Sprint {data.sprint_id} is not open")

    if sprint.spent_usd + estimated_usd > sprint.max_spend_usd:
        raise VosError(
            ErrorCode.BUDGET_EXCEEDED,
            f"Generation would exceed sprint budget "
            f"(remaining ${sprint.max_spend_usd - sprint.spent_usd:.2f}, "
            f"estimated ${estimated_usd:.2f})",
        )

    if sprint.max_videos is not None:
        video_count_result = await session.execute(
            select(func.count()).where(
                Asset.sprint_id == sprint.id,
                Asset.provider.in_(["higgsfield", "higgsfield_mcp"]),
            )
        )
        video_count = video_count_result.scalar_one()
        if video_count >= sprint.max_videos:
            raise VosError(
                ErrorCode.BUDGET_EXCEEDED,
                f"Sprint video limit reached ({sprint.max_videos} videos allowed)",
            )

    return BudgetLimit(max_spend_usd=sprint.max_spend_usd, max_videos=sprint.max_videos)


async def _submit_and_register(
    adapter: Any,
    data: ApiVideoInput,
    params: GenerationParams,
    estimated_usd: float,
    usage_event_id: str | None,
) -> tuple[str, str]:
    """Submit the provider job and persist the asset under a row-level lock.

    Re-validates budget under ``SELECT … FOR UPDATE`` to close the concurrency
    window (Fix #67), submits to the provider, creates the Asset with its usage
    linkage, and increments ``sprint.spent_usd`` by the estimate. Returns
    ``(asset_id, job_id)``.
    """
    async with get_session() as session:
        await set_tenant_context(session, data.client_id)

        result = await session.execute(
            select(Sprint).where(Sprint.id == uuid.UUID(data.sprint_id)).with_for_update()
        )
        sprint = result.scalar_one_or_none()
        if sprint is None:  # pragma: no cover — already checked above
            raise VosError(ErrorCode.NOT_FOUND, f"Sprint {data.sprint_id} not found")

        # Re-validate budget under the lock to catch concurrent submissions.
        if sprint.spent_usd + estimated_usd > sprint.max_spend_usd:
            raise VosError(
                ErrorCode.BUDGET_EXCEEDED,
                f"Generation would exceed sprint budget "
                f"(remaining ${sprint.max_spend_usd - sprint.spent_usd:.2f}, "
                f"estimated ${estimated_usd:.2f})",
            )

        log.info(
            "generation.requested",
            extra={"sprint_id": data.sprint_id, "provider": data.provider},
        )
        gen_result = await adapter.generate_video(params)
        log.info(
            "generation.provider_submitted",
            extra={
                "sprint_id": data.sprint_id,
                "job_id": gen_result.job_id,
                "provider": data.provider,
            },
        )

        asset = Asset(
            sprint_id=sprint.id,
            provider=data.provider,
            prompt_version=data.prompt_version,
            preset_version=data.preset_version,
            storage_url=None,
            provider_job_id=gen_result.job_id,
            generation_status="pending",
            storage_status="not_required",
            provider_usage_event_id=uuid.UUID(usage_event_id) if usage_event_id else None,
        )
        session.add(asset)

        sprint.spent_usd += estimated_usd
        await session.commit()
        await session.refresh(asset)

    return str(asset.id), gen_result.job_id


async def _emit_request_audit(data: ApiVideoInput, asset_id: str, estimated_usd: float) -> None:
    """Emit the audit event for an accepted API video generation request."""
    await emit_audit_event(
        action=AuditAction.API_VIDEO_REQUESTED,
        entity_type="asset",
        entity_id=asset_id,
        actor=data.client_id,
        provider=data.provider,
        mode="api_credits",
        cost_estimate_usd=estimated_usd,
        approval_status="approved",
        result=AuditResult.SUCCESS,
    )


# Fix #65: Summary and next_action are now storage-status-aware when generation
# is "completed". The simple dict lookup is replaced by a function that checks
# both generation_status and storage_status.

_NEXT_ACTION: dict[str, str] = {
    "pending": "get_video_job_status",
    "processing": "get_video_job_status",
    "failed": "request_api_video",
    "manual": "list_sprint_assets",
}

_SUMMARY: dict[str, str] = {
    "pending": "Video generation is queued. Poll again shortly.",
    "processing": "Video generation is in progress. Poll again shortly.",
    "failed": "Video generation failed. You may retry with request_api_video.",
    "manual": "Asset was registered manually — no generation job.",
}


def _resolve_summary(generation_status: str, storage_status: str) -> str:
    """Return a summary that reflects both generation and storage status."""
    if generation_status == "completed":
        if storage_status == "stored":
            return "Video is ready in storage."
        if storage_status == "failed":
            return "Generation complete but storage upload failed."
        # pending or any other transitional state
        return "Generation complete — upload to storage in progress."
    return _SUMMARY.get(generation_status, f"Unknown status: {generation_status}")


def _resolve_next_action(generation_status: str, storage_status: str) -> str:
    """Return the recommended next action based on both statuses."""
    if generation_status == "completed":
        if storage_status == "stored":
            return "prepare_dashboard_pack"
        # still uploading or upload failed — poll again
        return "get_video_job_status"
    return _NEXT_ACTION.get(generation_status, "get_video_job_status")


async def get_video_job_status(asset_id: str) -> VideoJobStatusResponse:
    """Return generation status for an asset without calling the provider API."""
    async with get_session() as session:
        asset, client_id = await get_asset_with_client(session, asset_id)

    if asset is None or client_id is None:
        raise VosError(ErrorCode.NOT_FOUND, f"Asset {asset_id} not found")

    assert_owns_client(client_id)

    gen_status = asset.generation_status
    stor_status = asset.storage_status
    return VideoJobStatusResponse(
        status="ok",
        asset_id=asset_id,
        generation_status=gen_status,
        storage_status=stor_status,
        storage_url=asset.storage_url,
        provider_job_id=asset.provider_job_id,
        summary=_resolve_summary(gen_status, stor_status),
        next_action=_resolve_next_action(gen_status, stor_status),
    )


async def list_video_jobs(sprint_id: str, client_id: str) -> ListVideoJobsResponse:
    """Return all API-generated assets for a sprint with aggregated status counts.

    Only returns assets with a provider_job_id (API-generated). Manual assets
    are excluded. Respects RLS — client_id must own the sprint.
    """
    assert_owns_client(client_id)

    async with get_session() as session:
        await set_tenant_context(session, client_id)

        sprint = await session.get(Sprint, uuid.UUID(sprint_id))
        if sprint is None:
            raise VosError(ErrorCode.NOT_FOUND, f"Sprint {sprint_id} not found")
        if str(sprint.client_id) != client_id:
            raise VosError(ErrorCode.INVALID_INPUT, "sprint does not belong to this client")

        result = await session.execute(
            select(Asset)
            .where(
                Asset.sprint_id == uuid.UUID(sprint_id),
                Asset.provider_job_id.is_not(None),
            )
            .order_by(Asset.created_at.desc())
        )
        assets = list(result.scalars().all())

    jobs = [
        VideoJobSummary(
            asset_id=str(a.id),
            provider_job_id=a.provider_job_id,
            generation_status=a.generation_status,
            storage_status=a.storage_status,
            storage_url=a.storage_url,
        )
        for a in assets
    ]

    counts = JobCounts(
        total=len(jobs),
        completed=sum(1 for j in jobs if j.generation_status == "completed"),
        processing=sum(1 for j in jobs if j.generation_status == "processing"),
        pending=sum(1 for j in jobs if j.generation_status == "pending"),
        failed=sum(1 for j in jobs if j.generation_status == "failed"),
    )

    all_done = counts.completed + counts.failed == counts.total
    any_processing = counts.processing > 0 or counts.pending > 0
    next_action = (
        "prepare_dashboard_pack" if all_done and counts.completed > 0
        else "poll_again" if any_processing
        else "request_api_video"
    )

    return ListVideoJobsResponse(
        status="ok",
        sprint_id=sprint_id,
        jobs=jobs,
        summary=counts,
        next_action=next_action,
    )
