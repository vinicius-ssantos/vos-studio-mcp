"""SSRF guard for outbound webhook URLs (Issue #47, ADR-0032, ADR-0040).

Validates that a URL is safe to use for outbound HTTP requests and returns
the pre-validated IP address.  The caller MUST connect to that IP (not
re-resolve the hostname) to prevent DNS-rebinding attacks (ADR-0040):

    # Registration — validate only (sync, ignore returned IP):
    validate_webhook_url(url)

    # Delivery — validate and get the IP to pin (async):
    pinned_ip = await check_webhook_url(url)

Addresses validated in order:
  - Non-HTTPS schemes
  - Loopback addresses (127.x, ::1)
  - RFC 1918 private networks (10.x, 172.16–31.x, 192.168.x)
  - Link-local addresses (169.254.x.x — includes cloud metadata endpoints)
  - Multicast and unspecified addresses
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from vos_studio_mcp.errors import ErrorCode, VosError

# All cloud providers (AWS, GCP, Azure) serve instance metadata here.
_CLOUD_METADATA_IP = ipaddress.ip_address("169.254.169.254")


def _is_public_ip(ip_str: str) -> bool:
    """Return True only if *ip_str* is a valid, globally routable address."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    if addr == _CLOUD_METADATA_IP:
        return False

    return not any(
        [
            addr.is_loopback,
            addr.is_private,
            addr.is_link_local,
            addr.is_multicast,
            addr.is_unspecified,
            addr.is_reserved,
        ]
    )


def validate_webhook_url(url: str) -> str:
    """Raise :class:`VosError` (``INVALID_INPUT``) if *url* is not SSRF-safe.
    Returns the pre-validated IP address to use for the outbound connection.

    Callers MUST connect to the returned IP (not re-resolve) to prevent
    DNS-rebinding attacks — see ADR-0040.

    Checks:
    1. URL must be parseable.
    2. Scheme must be ``https``.
    3. Hostname must be present.
    4. IP literal → must be publicly routable; returned directly.
    5. Hostname → every DNS-resolved IP must be publicly routable; the
       first resolved IP is returned as the pinned address.
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise VosError(ErrorCode.INVALID_INPUT, "Webhook URL is not a valid URL.") from exc

    if parsed.scheme != "https":
        raise VosError(
            ErrorCode.INVALID_INPUT,
            f"Webhook URL must use HTTPS (got scheme {parsed.scheme!r}).",
        )

    host = parsed.hostname  # lowercase, brackets stripped for IPv6 literals
    if not host:
        raise VosError(ErrorCode.INVALID_INPUT, "Webhook URL must include a hostname.")

    # --- IP literal fast-path — no DNS, return the IP directly ---
    try:
        addr = ipaddress.ip_address(host)
        if not _is_public_ip(str(addr)):
            raise VosError(
                ErrorCode.INVALID_INPUT,
                "Webhook URL must point to a publicly routable address, "
                "not a private, loopback, or link-local IP.",
            )
        return str(addr)
    except ValueError:
        pass  # not an IP literal — proceed to DNS resolution

    # --- Hostname DNS resolution ---
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise VosError(
            ErrorCode.INVALID_INPUT,
            f"Webhook URL hostname {host!r} could not be resolved: {exc}",
        ) from exc

    if not infos:
        raise VosError(
            ErrorCode.INVALID_INPUT,
            f"Webhook URL hostname {host!r} resolved to no addresses.",
        )

    pinned_ip: str | None = None
    for _family, _type, _proto, _canonname, sockaddr in infos:
        resolved_ip = str(sockaddr[0])
        if not _is_public_ip(resolved_ip):
            raise VosError(
                ErrorCode.INVALID_INPUT,
                "Webhook URL must point to a publicly routable address, "
                "not a private, loopback, or link-local IP.",
            )
        if pinned_ip is None:
            pinned_ip = resolved_ip  # pin to first validated IP

    return pinned_ip  # type: ignore[return-value]  # at least one infos entry validated above


async def check_webhook_url(url: str) -> str:
    """Async entry-point: run :func:`validate_webhook_url` in a thread pool.

    Returns the pre-validated IP address to use for the outbound connection.
    This prevents DNS resolution from blocking the event loop.
    Raises :class:`VosError` on any SSRF violation.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, validate_webhook_url, url)
