"""Audit event persistence service (ADR-0015).

Every paid, external, delivery, approval, or asset-changing action must call
emit_audit_event(). The function is fire-and-forget-safe: it swallows all
exceptions so audit failures never break the primary workflow.
"""

import logging
import uuid

from db.models import AuditLog
from vos_studio_mcp.auth.context import get_current_client_id
from vos_studio_mcp.services.database import bypass_rls, get_session

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Action constants (extend as new actions are added)
# ---------------------------------------------------------------------------


class AuditAction:
    # Paid / external generation
    API_VIDEO_REQUESTED = "api_video_requested"
    POLL_JOB_COMPLETED = "poll_job_completed"
    POLL_JOB_FAILED = "poll_job_failed"
    # Storage / delivery
    UPLOAD_COMPLETED = "upload_completed"
    UPLOAD_FAILED = "upload_failed"
    # Webhooks
    WEBHOOK_JOB_COMPLETED = "webhook_job_completed"
    WEBHOOK_JOB_FAILED = "webhook_job_failed"
    # Asset / sprint lifecycle
    SPRINT_CREATED = "sprint_created"
    SPRINT_CLOSED = "sprint_closed"
    MANUAL_ASSET_REGISTERED = "manual_asset_registered"
    # Creative operations
    VARIANT_TEST_CONCLUDED = "variant_test_concluded"
    PROMPT_PROMOTED = "prompt_promoted_to_library"
    PERFORMANCE_RECORDED = "performance_recorded"
    BLUEPRINT_PREPARED = "blueprint_prepared"


# ---------------------------------------------------------------------------
# Result constants
# ---------------------------------------------------------------------------


class AuditResult:
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def emit_audit_event(
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    result: str = AuditResult.SUCCESS,
    actor: str | None = None,
    provider: str | None = None,
    mode: str | None = None,
    cost_estimate_usd: float | None = None,
    approval_status: str | None = None,
    failure_reason: str | None = None,
) -> None:
    """Persist an audit event to the audit_logs table.

    Never raises — exceptions are caught and logged as warnings so that audit
    failures do not disrupt the primary workflow.
    """
    resolved_actor = actor or get_current_client_id() or "system"
    try:
        async with get_session() as session:
            await bypass_rls(session)
            event = AuditLog(
                id=uuid.uuid4(),
                actor=resolved_actor,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                provider=provider,
                mode=mode,
                cost_estimate_usd=cost_estimate_usd,
                approval_status=approval_status,
                result=result,
                failure_reason=failure_reason,
            )
            session.add(event)
            await session.commit()
    except Exception as exc:
        log.warning(
            "audit_event_write_failed",
            extra={
                "action": action,
                "entity_id": entity_id,
                "reason": str(exc),
            },
        )
