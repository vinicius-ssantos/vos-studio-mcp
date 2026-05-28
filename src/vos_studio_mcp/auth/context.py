"""Request-scoped auth context (ADR-0019)."""

from contextvars import ContextVar

_current_client_id: ContextVar[str | None] = ContextVar("current_client_id", default=None)


def get_current_client_id() -> str | None:
    """Return the client_id extracted from the validated bearer token."""
    return _current_client_id.get()


def set_current_client_id(client_id: str | None) -> None:
    _current_client_id.set(client_id)
