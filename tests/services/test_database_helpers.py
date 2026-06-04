"""Unit tests for services/database.py helper functions.

get_session, get_asset_with_client, set_tenant_context_from_sprint,
bypass_rls, get_asset_by_job_id, and set_tenant_context are tested with
mocked AsyncSession objects so no real database is required.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import InternalError as SAInternalError

from vos_studio_mcp.errors import ErrorCode, VosError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CLIENT_ID = "00000000-0000-0000-0000-000000000001"


def _scalar_result(value: object) -> MagicMock:
    """Return a mock execute() result where scalar_one_or_none() returns *value*."""
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=value)
    return r


def _row_result(row: object) -> MagicMock:
    """Return a mock execute() result where first() returns *row*."""
    r = MagicMock()
    r.first = MagicMock(return_value=row)
    return r


def _make_session(*execute_returns: object, get_return: object = None) -> AsyncMock:
    """Return an AsyncMock session whose execute() calls return execute_returns in order."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=list(execute_returns))
    session.get = AsyncMock(return_value=get_return)
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# get_session
# ---------------------------------------------------------------------------


def _rls_internal_error() -> SAInternalError:
    """Build a SQLAlchemy InternalError that mimics a PostgreSQL RLS violation."""
    orig = Exception("new row violates row-level security policy for table \"sprints\"")
    return SAInternalError("", {}, orig)


@pytest.mark.asyncio
async def test_get_session_yields_session_from_factory() -> None:
    from vos_studio_mcp.services.database import get_session

    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("vos_studio_mcp.services.database._session_factory", return_value=mock_ctx):  # noqa: SIM117
        async with get_session() as session:
            assert session is mock_session


@pytest.mark.asyncio
async def test_get_session_maps_rls_violation_to_vos_error() -> None:
    """An InternalError whose orig contains 'row-level security' must be
    re-raised as VosError(RLS_DENIED) so callers get a clean typed error."""
    from vos_studio_mcp.services.database import get_session

    mock_session = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("vos_studio_mcp.services.database._session_factory", return_value=mock_ctx):  # noqa: SIM117
        with pytest.raises(VosError) as exc_info:
            async with get_session():
                raise _rls_internal_error()

    assert exc_info.value.error_code == ErrorCode.RLS_DENIED


@pytest.mark.asyncio
async def test_get_session_reraises_non_rls_internal_error() -> None:
    """InternalError unrelated to RLS must propagate unchanged."""
    from vos_studio_mcp.services.database import get_session

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    other_error = SAInternalError("", {}, Exception("deadlock detected"))

    with patch("vos_studio_mcp.services.database._session_factory", return_value=mock_ctx):  # noqa: SIM117
        with pytest.raises(SAInternalError):
            async with get_session():
                raise other_error


# ---------------------------------------------------------------------------
# bypass_rls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bypass_rls_executes_set_row_security_off() -> None:
    from vos_studio_mcp.services.database import bypass_rls

    session = _make_session(MagicMock())
    await bypass_rls(session)
    session.execute.assert_awaited_once()
    sql = str(session.execute.call_args[0][0])
    assert "row_security" in sql


# ---------------------------------------------------------------------------
# set_tenant_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_tenant_context_calls_set_config() -> None:
    from vos_studio_mcp.services.database import set_tenant_context

    session = _make_session(MagicMock())
    await set_tenant_context(session, _CLIENT_ID)
    session.execute.assert_awaited_once()
    _sql, params = session.execute.call_args[0][0], session.execute.call_args[0][1]
    assert params["cid"] == _CLIENT_ID


# ---------------------------------------------------------------------------
# get_asset_with_client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_asset_with_client_returns_asset_and_client_id() -> None:
    from vos_studio_mcp.services.database import get_asset_with_client

    asset_id = str(uuid.uuid4())
    asset_mock = MagicMock()

    # execute calls: vos_get_asset_client_id | set_tenant_context
    session = _make_session(
        _scalar_result(_CLIENT_ID),
        MagicMock(),
        get_return=asset_mock,
    )

    asset, client_id = await get_asset_with_client(session, asset_id)

    assert asset is asset_mock
    assert client_id == _CLIENT_ID


@pytest.mark.asyncio
async def test_get_asset_with_client_returns_none_when_not_found() -> None:
    from vos_studio_mcp.services.database import get_asset_with_client

    # execute calls: vos_get_asset_client_id (returns None — asset not found)
    session = _make_session(_scalar_result(None))

    asset, client_id = await get_asset_with_client(session, str(uuid.uuid4()))

    assert asset is None
    assert client_id is None


# ---------------------------------------------------------------------------
# set_tenant_context_from_sprint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_tenant_context_from_sprint_returns_client_id() -> None:
    from vos_studio_mcp.services.database import set_tenant_context_from_sprint

    sprint_id = str(uuid.uuid4())

    # execute calls: vos_get_sprint_client_id | set_tenant_context
    session = _make_session(
        _scalar_result(_CLIENT_ID),
        MagicMock(),
    )

    client_id = await set_tenant_context_from_sprint(session, sprint_id)

    assert client_id == _CLIENT_ID


@pytest.mark.asyncio
async def test_set_tenant_context_from_sprint_raises_when_sprint_not_found() -> None:
    from vos_studio_mcp.services.database import set_tenant_context_from_sprint

    # execute calls: vos_get_sprint_client_id (returns None — sprint not found)
    session = _make_session(_scalar_result(None))

    with pytest.raises(LookupError, match="not found"):
        await set_tenant_context_from_sprint(session, str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# get_asset_notification_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_asset_notification_context_returns_tuple_when_found() -> None:
    """Must return (sprint_id, client_id, webhook_url) for a known asset."""
    asset_id = str(uuid.uuid4())
    sprint_id = str(uuid.uuid4())
    webhook = "https://client.example.com/hook"

    mock_ctx = MagicMock()
    # execute calls: vos_get_asset_notification_context SELECT
    session = _make_session(_row_result((sprint_id, _CLIENT_ID, webhook)))
    mock_ctx.__aenter__ = AsyncMock(return_value=session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("vos_studio_mcp.services.database._session_factory", return_value=mock_ctx):
        from vos_studio_mcp.services.database import get_asset_notification_context
        s_id, c_id, w_url = await get_asset_notification_context(asset_id)

    assert s_id == sprint_id
    assert c_id == _CLIENT_ID
    assert w_url == webhook


@pytest.mark.asyncio
async def test_get_asset_notification_context_returns_nones_when_not_found() -> None:
    """Must return (None, None, None) when the asset does not exist."""
    asset_id = str(uuid.uuid4())

    mock_ctx = MagicMock()
    # execute calls: vos_get_asset_notification_context SELECT (no row)
    session = _make_session(_row_result(None))
    mock_ctx.__aenter__ = AsyncMock(return_value=session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("vos_studio_mcp.services.database._session_factory", return_value=mock_ctx):
        from vos_studio_mcp.services.database import get_asset_notification_context
        result = await get_asset_notification_context(asset_id)

    assert result == (None, None, None)


# ---------------------------------------------------------------------------
# get_asset_by_job_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_asset_by_job_id_returns_ids_when_found() -> None:
    from vos_studio_mcp.services.database import get_asset_by_job_id

    asset_id = str(uuid.uuid4())
    row = (asset_id, _CLIENT_ID)

    session = _make_session(_row_result(row))
    result_asset_id, result_client_id = await get_asset_by_job_id(session, "job-123")

    assert result_asset_id == asset_id
    assert result_client_id == _CLIENT_ID


@pytest.mark.asyncio
async def test_get_asset_by_job_id_returns_none_when_not_found() -> None:
    from vos_studio_mcp.services.database import get_asset_by_job_id

    session = _make_session(_row_result(None))
    result_asset_id, result_client_id = await get_asset_by_job_id(session, "job-unknown")

    assert result_asset_id is None
    assert result_client_id is None
