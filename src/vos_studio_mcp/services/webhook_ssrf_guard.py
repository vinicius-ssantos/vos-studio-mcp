"""SSRF guard for outbound webhook URLs (Issue #47, ADR-0032).

Validates that a URL is safe to use for outbound HTTP requests.  Prevents
Server-Side Request Forgery by rejecting URLs that resolve to:

  - Non-HTTPS schemes
  - Loopback addresses (127.x, ::1)
  - RFC 1918 private networks (10.x, 172.16–31.x, 192.168.x)
  - Link-local addresses (169.254.x.x — includes cloud metadata endpoints)
  - Multicast and unspecified addresses

Two entry points:
  validate_webhook_url(url)   — synchronous, raises VosError on violation.
                                Safe for Celery / test contexts.
  check_webhook_url(url)      — async wrapper; runs DNS in a thread pool so
                                the event loop is never blocked.

Usage:
    # Registration (sync context is fine):
    validate_webhook_url(input_url)

    # Inside async delivery (_deliver):
    await check_webhook_url(webhook_url)
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from vos_studio_mcp.errors import ErrorCode, VosError

# All cloud providers (AWS, GCP, Azure) serve instance metadata here.
# 169.254.x.x is already link-local, but naming it explicitly improves
# clarity in error messages and tests.
_CLOUD_METADATA_IP = ipaddress.ip_address("169.254.169.254")


def _is_public_ip(ip_str: str) -> bool:
    """Return True only if *ip_str* is a valid, globally routable address."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False  # not parseable — treat as unsafe

    # Cloud metadata endpoint check (redundant with is_link_local but explicit).
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


def validate_webhook_url(url: str) -> None:
    """Raise :class:`VosError` (``INVALID_INPUT``) if *url* is not SSRF-safe.

    Checks performed, in order:
    1. URL must be parseable.
    2. Scheme must be ``https``.
    3. Hostname must be present.
    4. If the hostname is an IP literal, it must be publicly routable.
    5. If the hostname is a domain name, every DNS-resolved IP must be
       publicly routable (blocks DNS rebinding to private addresses).
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

    # --- IP literal fast-path ---
    try:
        addr = ipaddress.ip_address(host)
        if not _is_public_ip(str(addr)):
            raise VosError(
                ErrorCode.INVALID_INPUT,
                "Webhook URL must point to a publicly routable address, "
                "not a private, loopback, or link-local IP.",
            )
        return
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

    for _family, _type, _proto, _canonname, sockaddr in infos:
        resolved_ip = str(sockaddr[0])
        if not _is_public_ip(resolved_ip):
            raise VosError(
                ErrorCode.INVALID_INPUT,
                "Webhook URL must point to a publicly routable address, "
                "not a private, loopback, or link-local IP.",
            )


async def check_webhook_url(url: str) -> None:
    """Async entry-point: run :func:`validate_webhook_url` in a thread pool.

    This prevents DNS resolution from blocking the event loop.
    Raises :class:`VosError` on any SSRF violation.
    """
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, validate_webhook_url, url)
