"""Unit tests for prompt_library_service (ADR-0029)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from vos_studio_mcp.errors import ErrorCode, VosError
from vos_studio_mcp.schemas.prompt_template import PromoteToLibraryInput

_SERVICE = "vos_studio_mcp.services.prompt_library_service"
_GET_SESSION = f"{_SERVICE}.get_session"

_VALID_TEMPLATE = "Show {{product_name}} with limited stock messaging for {{brand_name}}"


@pytest.fixture
def mock_session_ctx(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    session = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(_GET_SESSION, lambda: cm)
    return session


def _valid_input(**kwargs: object) -> PromoteToLibraryInput:
    defaults: dict[str, object] = {
        "sprint_id": str(uuid.uuid4()),
        "prompt_version": "v1",
        "name": "Urgency + scarcity for conversion",
        "description": "Drives CTR with limited availability framing",
        "industry": ["skincare", "e-commerce"],
        "format": ["video_ad"],
        "objective": ["conversion"],
        "platform": ["meta"],
        "prompt_template": _VALID_TEMPLATE,
        "confirmed": True,
    }
    defaults.update(kwargs)
    return PromoteToLibraryInput(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Preview mode (confirmed=False)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_returns_checklist_without_db(monkeypatch: pytest.MonkeyPatch) -> None:
    from vos_studio_mcp.services.prompt_library_service import promote_to_library

    data = PromoteToLibraryInput(
        sprint_id=str(uuid.uuid4()),
        prompt_version="v1",
        name="Test",
        description="desc",
        prompt_template=_VALID_TEMPLATE,
        confirmed=False,
    )
    result = await promote_to_library(data, "operator@example.com")

    assert result.status == "preview"
    assert result.template_id is None
    assert len(result.anonymization_checklist) > 0
    assert result.next_action == "promote_to_library"


# ---------------------------------------------------------------------------
# Successful promotion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promote_creates_template(mock_session_ctx: MagicMock) -> None:
    from vos_studio_mcp.services.prompt_library_service import promote_to_library

    sprint = MagicMock()
    sprint.id = uuid.uuid4()
    mock_session_ctx.get = AsyncMock(return_value=sprint)

    saved_template: MagicMock | None = None

    def capture_add(obj: object) -> None:
        nonlocal saved_template
        saved_template = obj  # type: ignore[assignment]

    mock_session_ctx.add = MagicMock(side_effect=capture_add)
    mock_session_ctx.refresh = AsyncMock(side_effect=lambda obj: None)

    data = _valid_input()
    result = await promote_to_library(data, "operator@example.com")

    assert result.status == "created"
    assert result.performance_tier == "experimental"
    assert result.template_id is not None
    assert result.next_action == "create_creative_sprint"
    mock_session_ctx.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sprint_not_found_raises(mock_session_ctx: MagicMock) -> None:
    from vos_studio_mcp.services.prompt_library_service import promote_to_library

    mock_session_ctx.get = AsyncMock(return_value=None)

    data = _valid_input()
    with pytest.raises(VosError) as exc_info:
        await promote_to_library(data, "op")
    assert exc_info.value.error_code == ErrorCode.NOT_FOUND


@pytest.mark.asyncio
async def test_missing_placeholder_raises(mock_session_ctx: MagicMock) -> None:
    from vos_studio_mcp.services.prompt_library_service import promote_to_library

    sprint = MagicMock()
    mock_session_ctx.get = AsyncMock(return_value=sprint)

    # No {{placeholder}} in template
    data = _valid_input(prompt_template="A generic video about the product launch.")
    with pytest.raises(VosError) as exc_info:
        await promote_to_library(data, "op")
    assert exc_info.value.error_code == ErrorCode.VALIDATION_ERROR


# ---------------------------------------------------------------------------
# Library suggestions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_library_suggestions_filters_deprecated(
    mock_session_ctx: MagicMock,
) -> None:
    from vos_studio_mcp.services.prompt_library_service import get_library_suggestions

    t1 = MagicMock()
    t1.id = uuid.uuid4()
    t1.name = "Template A"
    t1.performance_tier = "proven"
    t1.avg_ctr = 0.038
    t1.prompt_template = "Show {{product_name}} with urgency"
    t1.industry = ["skincare"]
    t1.format = ["video_ad"]
    t1.objective = ["conversion"]
    t1.platform = ["meta"]

    scalars_result = MagicMock()
    scalars_result.__iter__ = MagicMock(return_value=iter([t1]))
    mock_session_ctx.scalars = AsyncMock(return_value=scalars_result)

    suggestions = await get_library_suggestions(
        industry=["skincare"],
        format=["video_ad"],
        objective=["conversion"],
        platform=["meta"],
    )

    assert len(suggestions) == 1
    assert suggestions[0].name == "Template A"
    assert suggestions[0].performance_tier == "proven"
    assert suggestions[0].avg_ctr == 0.038


@pytest.mark.asyncio
async def test_get_library_suggestions_no_match_returns_empty(
    mock_session_ctx: MagicMock,
) -> None:
    from vos_studio_mcp.services.prompt_library_service import get_library_suggestions

    t1 = MagicMock()
    t1.id = uuid.uuid4()
    t1.name = "Template B"
    t1.performance_tier = "experimental"
    t1.avg_ctr = None
    t1.prompt_template = "Show {{product_name}}"
    t1.industry = ["fintech"]
    t1.format = ["static_image"]
    t1.objective = ["awareness"]
    t1.platform = ["google"]

    scalars_result = MagicMock()
    scalars_result.__iter__ = MagicMock(return_value=iter([t1]))
    mock_session_ctx.scalars = AsyncMock(return_value=scalars_result)

    suggestions = await get_library_suggestions(
        industry=["skincare"],
        format=["video_ad"],
        objective=["conversion"],
        platform=["meta"],
    )

    assert suggestions == []
