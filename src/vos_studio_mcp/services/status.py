"""Server status service."""

from vos_studio_mcp import __version__
from vos_studio_mcp.config.env import Settings
from vos_studio_mcp.schemas.status import ServerStatus


def get_server_status(settings: Settings) -> ServerStatus:
    """Return a compact status payload."""

    return ServerStatus(
        service=settings.mcp_server_name,
        version=__version__,
        next_action="create_client",
    )
