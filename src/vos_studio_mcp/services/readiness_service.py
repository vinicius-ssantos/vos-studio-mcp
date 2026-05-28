"""Generation readiness check — validates all preconditions before request_api_video."""

import uuid

from db.models import Sprint
from vos_studio_mcp.config.env import get_settings
from vos_studio_mcp.schemas.readiness import GenerationReadinessResponse, ReadinessBlocker
from vos_studio_mcp.services.circuit_breaker import get_breaker
from vos_studio_mcp.services.database import get_session, set_tenant_context
from vos_studio_mcp.services.providers.capabilities import (
    get_all_provider_ids,
    get_provider_capability,
)


async def check_generation_readiness(
    provider: str,
    sprint_id: str,
    client_id: str,
) -> GenerationReadinessResponse:
    blockers: list[ReadinessBlocker] = []
    settings = get_settings()

    # 1. Provider known
    if provider not in get_all_provider_ids(include_disabled=True):
        blockers.append(ReadinessBlocker(
            check="provider_known",
            reason=f"Provider '{provider}' is not registered.",
            action="Call list_provider_capabilities to see available providers.",
        ))
        return _response(provider, sprint_id, blockers)

    # 2. Provider enabled
    cap = get_provider_capability(provider)
    if not cap.default_enabled:
        blockers.append(ReadinessBlocker(
            check="provider_enabled",
            reason=f"Provider '{provider}' is disabled by default.",
            action="Set the corresponding *_ENABLED env var to true and restart.",
        ))

    # 3. Circuit breaker
    breaker = get_breaker(
        provider,
        failure_threshold=cap.circuit_breaker_failure_threshold,
        recovery_timeout=cap.circuit_breaker_timeout_s,
    )
    if breaker.state == "open":
        blockers.append(ReadinessBlocker(
            check="circuit_breaker",
            reason=f"Circuit breaker for '{provider}' is open ({breaker.failure_count} failures).",
            action="Wait for recovery timeout or call reset_circuit_breaker.",
        ))
    elif breaker.state == "half_open":
        pass  # half_open allows a trial call — not a hard blocker

    # 4. Token configured (for MCP-backed providers)
    if provider == "higgsfield_mcp":
        if not settings.higgsfield_mcp_enabled:
            blockers.append(ReadinessBlocker(
                check="provider_token",
                reason="HIGGSFIELD_MCP_ENABLED is false.",
                action="Set HIGGSFIELD_MCP_ENABLED=true.",
            ))
        elif not settings.higgsfield_mcp_access_token:
            blockers.append(ReadinessBlocker(
                check="provider_token",
                reason="HIGGSFIELD_MCP_ACCESS_TOKEN is not configured.",
                action="Set HIGGSFIELD_MCP_ACCESS_TOKEN in the environment.",
            ))
    elif provider == "higgsfield" and not settings.higgsfield_api_key:
        blockers.append(ReadinessBlocker(
            check="provider_token",
            reason="HIGGSFIELD_API_KEY is not configured.",
            action="Set HIGGSFIELD_API_KEY in the environment.",
        ))

    # 5. Sprint open + budget available
    try:
        async with get_session() as session:
            await set_tenant_context(session, client_id)
            sprint = await session.get(Sprint, uuid.UUID(sprint_id))
            if sprint is None:
                blockers.append(ReadinessBlocker(
                    check="sprint_exists",
                    reason=f"Sprint {sprint_id} not found.",
                    action="Verify sprint_id or call create_creative_sprint.",
                ))
            else:
                if str(sprint.client_id) != client_id:
                    blockers.append(ReadinessBlocker(
                        check="sprint_ownership",
                        reason="Sprint does not belong to this client.",
                        action="Use a sprint_id that belongs to the authenticated client.",
                    ))
                elif sprint.sprint_status != "open":
                    blockers.append(ReadinessBlocker(
                        check="sprint_open",
                        reason=f"Sprint is '{sprint.sprint_status}', not open.",
                        action="Only open sprints accept new generation requests.",
                    ))
                elif sprint.spent_usd >= sprint.max_spend_usd:
                    blockers.append(ReadinessBlocker(
                        check="sprint_budget",
                        reason=(
                            f"Sprint budget exhausted "
                            f"(spent ${sprint.spent_usd:.2f} of ${sprint.max_spend_usd:.2f})."
                        ),
                        action="Increase sprint budget or start a new sprint.",
                    ))
    except Exception:
        # DB unavailable — skip sprint checks rather than block
        pass

    return _response(provider, sprint_id, blockers)


def _response(
    provider: str,
    sprint_id: str,
    blockers: list[ReadinessBlocker],
) -> GenerationReadinessResponse:
    ready = len(blockers) == 0
    if ready:
        summary = f"Provider '{provider}' is ready for generation on sprint {sprint_id}."
        next_action = "request_api_video"
    else:
        checks = ", ".join(b.check for b in blockers)
        summary = f"Generation blocked — {len(blockers)} issue(s): {checks}."
        next_action = blockers[0].action.split()[0].lower() if blockers else "review_blockers"

    return GenerationReadinessResponse(
        status="ready" if ready else "blocked",
        provider=provider,
        sprint_id=sprint_id,
        ready=ready,
        blockers=blockers,
        summary=summary,
        next_action=next_action if ready else "resolve_blockers",
    )
