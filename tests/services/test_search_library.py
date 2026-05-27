"""Unit tests for search_library service (Issue #32)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vos_studio_mcp.schemas.prompt_template import SearchLibraryInput
from vos_studio_mcp.services.prompt_library_service import search_library

_GET_SESSION = "vos_studio_mcp.services.prompt_library_service.get_session"


def _mock_template(
    name: str = "Video template",
    description: str = "A great template",
    prompt_template: str = "Create a {{brand_name}} video",
    performance_tier: str = "tested",
    usage_count: int = 10,
    avg_ctr: float | None = 0.05,
    industry: list[str] | None = None,
    format: list[str] | None = None,
    objective: list[str] | None = None,
    platform: list[str] | None = None,
    asset_stage: list[str] | None = None,
) -> MagicMock:
    t = MagicMock()
    t.id = "aaaaaaaa-0000-0000-0000-000000000001"
    t.name = name
    t.description = description
    t.prompt_template = prompt_template
    t.performance_tier = performance_tier
    t.usage_count = usage_count
    t.avg_ctr = avg_ctr
    t.industry = industry or ["retail"]
    t.format = format or ["video"]
    t.objective = objective or ["awareness"]
    t.platform = platform or ["instagram"]
    t.asset_stage = asset_stage or []
    return t


def _session_ctx(templates: list[MagicMock]) -> MagicMock:
    session = AsyncMock()
    session.scalars = AsyncMock(return_value=iter(templates))

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestSearchLibraryInput:
    def test_requires_at_least_one_filter(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SearchLibraryInput()

    def test_query_only_is_valid(self) -> None:
        data = SearchLibraryInput(query="video")
        assert data.query == "video"

    def test_industry_only_is_valid(self) -> None:
        data = SearchLibraryInput(industry=["retail"])
        assert data.industry == ["retail"]

    def test_min_tier_only_is_valid(self) -> None:
        data = SearchLibraryInput(min_tier="top_performer")
        assert data.min_tier == "top_performer"

    def test_asset_stage_only_is_valid(self) -> None:
        data = SearchLibraryInput(asset_stage=["stage_c"])
        assert data.asset_stage == ["stage_c"]

    def test_limit_defaults_to_10(self) -> None:
        data = SearchLibraryInput(query="x")
        assert data.limit == 10

    def test_limit_max_50(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SearchLibraryInput(query="x", limit=51)


class TestSearchLibraryService:
    @pytest.mark.asyncio
    async def test_returns_ok_status(self) -> None:
        ctx = _session_ctx([_mock_template()])
        with patch(_GET_SESSION, return_value=ctx):
            resp = await search_library(SearchLibraryInput(query="video"))
        assert resp.status == "ok"

    @pytest.mark.asyncio
    async def test_keyword_search_matches_name(self) -> None:
        templates = [
            _mock_template(name="Video brand template", prompt_template="Generic {{placeholder}}"),
            _mock_template(name="Unrelated post", prompt_template="Generic {{placeholder}}"),
        ]
        ctx = _session_ctx(templates)
        with patch(_GET_SESSION, return_value=ctx):
            resp = await search_library(SearchLibraryInput(query="brand"))
        assert resp.total == 1
        assert "brand" in resp.results[0].name.lower()

    @pytest.mark.asyncio
    async def test_keyword_search_matches_prompt_text(self) -> None:
        templates = [
            _mock_template(prompt_template="Create a {{brand_name}} promo clip"),
            _mock_template(prompt_template="Generic post content"),
        ]
        ctx = _session_ctx(templates)
        with patch(_GET_SESSION, return_value=ctx):
            resp = await search_library(SearchLibraryInput(query="promo"))
        assert resp.total == 1

    @pytest.mark.asyncio
    async def test_keyword_search_case_insensitive(self) -> None:
        ctx = _session_ctx([_mock_template(name="SUMMER CAMPAIGN")])
        with patch(_GET_SESSION, return_value=ctx):
            resp = await search_library(SearchLibraryInput(query="summer"))
        assert resp.total == 1

    @pytest.mark.asyncio
    async def test_industry_filter(self) -> None:
        templates = [
            _mock_template(name="Retail", industry=["retail"]),
            _mock_template(name="Fashion", industry=["fashion"]),
        ]
        ctx = _session_ctx(templates)
        with patch(_GET_SESSION, return_value=ctx):
            resp = await search_library(SearchLibraryInput(industry=["retail"]))
        assert resp.total == 1
        assert resp.results[0].name == "Retail"

    @pytest.mark.asyncio
    async def test_min_tier_filter(self) -> None:
        templates = [
            _mock_template(name="Top", performance_tier="top_performer"),
            _mock_template(name="Tested", performance_tier="tested"),
            _mock_template(name="Experimental", performance_tier="experimental"),
        ]
        ctx = _session_ctx(templates)
        with patch(_GET_SESSION, return_value=ctx):
            resp = await search_library(SearchLibraryInput(min_tier="tested", industry=["retail"]))
        names = [r.name for r in resp.results]
        assert "Top" in names
        assert "Tested" in names
        assert "Experimental" not in names

    @pytest.mark.asyncio
    async def test_top_performers_ranked_first(self) -> None:
        templates = [
            _mock_template(name="Experimental", performance_tier="experimental"),
            _mock_template(name="Top", performance_tier="top_performer"),
            _mock_template(name="Tested", performance_tier="tested"),
        ]
        ctx = _session_ctx(templates)
        with patch(_GET_SESSION, return_value=ctx):
            resp = await search_library(SearchLibraryInput(industry=["retail"]))
        assert resp.results[0].name == "Top"
        assert resp.results[1].name == "Tested"

    @pytest.mark.asyncio
    async def test_empty_result_returns_next_action_promote(self) -> None:
        ctx = _session_ctx([])
        with patch(_GET_SESSION, return_value=ctx):
            resp = await search_library(SearchLibraryInput(query="nonexistent"))
        assert resp.total == 0
        assert resp.next_action == "promote_to_library"

    @pytest.mark.asyncio
    async def test_result_with_matches_returns_next_action_blueprint(self) -> None:
        ctx = _session_ctx([_mock_template()])
        with patch(_GET_SESSION, return_value=ctx):
            resp = await search_library(SearchLibraryInput(query="video"))
        assert resp.next_action == "prepare_video_blueprint"

    @pytest.mark.asyncio
    async def test_asset_stage_filter(self) -> None:
        templates = [
            _mock_template(name="Stage C video", asset_stage=["stage_c"]),
            _mock_template(name="Stage A concept", asset_stage=["stage_a"]),
            _mock_template(name="Agnostic template", asset_stage=[]),
        ]
        ctx = _session_ctx(templates)
        with patch(_GET_SESSION, return_value=ctx):
            resp = await search_library(SearchLibraryInput(asset_stage=["stage_c"]))
        names = [r.name for r in resp.results]
        # stage_c match + agnostic match; stage_a excluded
        assert "Stage C video" in names
        assert "Agnostic template" in names
        assert "Stage A concept" not in names

    @pytest.mark.asyncio
    async def test_asset_stage_in_result(self) -> None:
        ctx = _session_ctx([_mock_template(asset_stage=["stage_c", "final"])])
        with patch(_GET_SESSION, return_value=ctx):
            resp = await search_library(SearchLibraryInput(query="video"))
        assert resp.results[0].asset_stage == ["stage_c", "final"]

    @pytest.mark.asyncio
    async def test_prompt_preview_truncated_to_300(self) -> None:
        long_prompt = "x" * 500
        ctx = _session_ctx([_mock_template(prompt_template=long_prompt)])
        with patch(_GET_SESSION, return_value=ctx):
            resp = await search_library(SearchLibraryInput(query="x"))
        assert len(resp.results[0].prompt_preview) == 300

    @pytest.mark.asyncio
    async def test_result_fields_are_mapped(self) -> None:
        t = _mock_template(
            name="My Template",
            performance_tier="top_performer",
            avg_ctr=0.12,
            usage_count=42,
        )
        ctx = _session_ctx([t])
        with patch(_GET_SESSION, return_value=ctx):
            resp = await search_library(SearchLibraryInput(query="template"))
        r = resp.results[0]
        assert r.name == "My Template"
        assert r.performance_tier == "top_performer"
        assert r.avg_ctr == 0.12
        assert r.usage_count == 42
