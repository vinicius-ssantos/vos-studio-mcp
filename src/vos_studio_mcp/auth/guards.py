"""Auth guard helpers — enforce client_id ownership (ADR-0019)."""

from vos_studio_mcp.auth.context import get_current_client_id
from vos_studio_mcp.errors import ErrorCode, VosError


def assert_owns_client(input_client_id: str) -> None:
    """Raise VosError if the auth context does not own the given client_id.

    No-op when auth context is not set (dev with auth disabled).
    """
    auth_client_id = get_current_client_id()
    if auth_client_id is None:
        return
    if auth_client_id != input_client_id:
        raise VosError(
            ErrorCode.INVALID_INPUT,
            "client_id does not match authenticated session",
        )
